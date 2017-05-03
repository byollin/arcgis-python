'''-------------------------------------------------------------------------------------------------
    Name:    ApplyRidership
    Purpose: Applies ridership volumes to street segments along the TNET (King County) street
             network.

    System Requirements:
        - ArcGIS 10.1, 10.2, or 10.3.
        - Python 2.* (.2 to .8) installed with ArcGIS. This must be the default Python version for
          the user.
        - All modules used are installed along with ArcGIS 10.1, 10.2 and 10.3.
            - The NetworkX module is not a standard Python library, it may need to be downloaded
              from the project website: https://pypi.python.org/pypi/networkx/

    Notes:

    Calls:
        N/A

    Called By:
        ArcGIS Python script tool

    Parameters:

-------------------------------------------------------------------------------------------------'''

import arcpy
import sys
import csv
import traceback
from collections import defaultdict

try:
    strNetworkX = 'M:\Devapps\HNSTS\Model Toolbox\Custom Modules'
    sys.path.append(strNetworkX)
    import networkx as nx
except ImportError:
    arcpy.AddError('\nError: NetworkX module is not accessible.')
    raise SystemExit()

# TNET feature class
fcStreets = arcpy.GetParameterAsText(0)

# route data provided by King County Metro
fcRoutes  = arcpy.GetParameterAsText(1)

# query from MetroTool
csvMetroQuery = arcpy.GetParameterAsText(2)

# output feature class
fcOut = arcpy.GetParameterAsText(3)

####################################################################################################

def CreateDirectedMultiGraph():

    """
    Creates a directed multigraph of the TNET.
    """

    try:

        G         = nx.MultiDiGraph()
        lstFields = ['FR_TPOINT', 'TO_TPOINT', 'TLINK_ID', 'CAR_FLOW', 'ROLL_LEN']

        with arcpy.da.SearchCursor(fcStreets, lstFields) as cursor:

            for row in cursor:

                ifrom = row[0]
                to    = row[1]
                tlink = row[2]
                flow  = row[3]

                if ifrom is not None and to is not None:

                    cost = row[4]

                    if flow == 2:
                        G.add_edge(to, ifrom, link=tlink, cost=cost, total=0)
                    elif flow == 1:
                        G.add_edge(ifrom, to, link=tlink, cost=cost, total=0)
                    else:
                        G.add_edge(ifrom, to, link=tlink, cost=cost, total=0)
                        G.add_edge(to, ifrom, link=tlink, cost=cost, total=0)

                else:
                    pass

        return G

    except:
        arcpy.AddError(traceback.format_exc())
        arcpy.AddError('\nError: Unable to construct TNET graph.')
        raise SystemExit()

####################################################################################################

def SubgraphDataLookup():

    """
    Generates a dictionary of segments traversed for each route. This information is used to create
    a `subgraph` which increases the efficiency and accuracy of the computed path between bus stops.
    """

    try:

        dictRouteSegments = defaultdict(list)
        with arcpy.da.SearchCursor(fcRoutes, ['ROUTE_NUM', 'TLINK_ID']) as cursor:
            for row in cursor:
                route = row[0]
                tlink = row[1]
                dictRouteSegments[route].append(tlink)

        return dictRouteSegments

    except Exception:
        arcpy.AddError(traceback.format_exc())
        arcpy.AddError('\nError: Unable to construct subgraph data.')
        raise SystemExit()

####################################################################################################

def RouteDataLookup():

    """
    Generates dictionaries containing route metrics extracted from MetroTool query. This includes
    data for average boardings and alightings per stop.
    """

    try:

        dictRouteMetrics = {'inbound': defaultdict(lambda: defaultdict(tuple)),
                            'outbound': defaultdict(lambda: defaultdict(tuple))}

        # total ons and offs for weighting
        dictRouteTotals = {'inbound': defaultdict(lambda: defaultdict(int)),
                           'outbound': defaultdict(lambda: defaultdict(int))}

        with open(csvMetroQuery, 'rb') as csv_file:
            reader = csv.reader(csv_file, delimiter=',')
            next(reader, None)
            for row in reader:
                route = int(row[0])
                dir   = row[1].lower()
                seq   = float(row[3])
                ons   = int(row[6])
                offs  = int(row[7])
                try:
                    tlink = int(row[8])
                except ValueError:
                    tlink = None

                dictRouteMetrics[dir][route][seq]   = [tlink, ons, offs]
                dictRouteTotals[dir][route]['ons']  += ons
                dictRouteTotals[dir][route]['offs'] += offs

        return (dictRouteMetrics, dictRouteTotals)

    except Exception:
        arcpy.AddError(traceback.format_exc())
        arcpy.AddError('\nError: Unable to extract route metrics.')
        raise SystemExit()

####################################################################################################

def NodeLookup(G):

    """
    Generates a dictionary for extracting nodes by TLINK_ID.
    """

    try:

        dictAllNodes = defaultdict(tuple)
        for edge in G.edges(data=('link', 'total')):
            data = G.get_edge_data(*edge)
            for k in data.keys():
                dictAllNodes[data[k]['link']] = (edge[0], edge[1])

        return dictAllNodes

    except:
        arcpy.AddError(traceback.format_exc())
        arcpy.AddError('\nError: Unable to construct TLINK lookup for graph.')
        raise SystemExit()

####################################################################################################

def CreateSubgraph(G, r, dictRouteSegments):

    """
    Creates a subgraph of the TNET defined by the provided 'nbunch' (fancy word for list of nodes).
    """

    try:

        dictRouteLinks = dictRouteSegments[r]
        dictRouteNodes = defaultdict(tuple)

        # logic for multi-edges
        for edge in G.edges(data=('link', 'total')):
            data = G.get_edge_data(*edge)
            for k in data.keys():
                if data[k]['link'] in dictRouteLinks:
                    dictRouteNodes[data[k]['link']] = (edge[0], edge[1])
                else:
                    pass

        # a 'nbunch' to pass to subgraph
        lstNodes = [n for tupNode in dictRouteNodes.values() for n in tupNode]
        subgraph = G.subgraph(lstNodes)

        # remove extraneous edges
        for edge in subgraph.edges(data='link'):
            if edge[2] not in dictRouteLinks:
                subgraph.remove_edge(edge[0], edge[1])

        return (dictRouteLinks, dictRouteNodes, subgraph)

    except:
        arcpy.AddError(traceback.format_exc())
        arcpy.AddError('\nError: Unable to create subgraph.')
        raise SystemExit()

####################################################################################################

def AdjustRidership(ons, offs, total_on, total_off):

    """
    Short function to adjust or weight ons and offs using available data.
    """

    if total_on > total_off:
        diff          = total_on - total_off
        adjusted_offs = offs + diff * (float(offs) / total_off)
        adjusted_ons  = ons
    else:
        diff          = total_off - total_on
        adjusted_ons  = ons + diff * (float(ons) / total_on)
        adjusted_offs = offs

    return (adjusted_ons, adjusted_offs)

####################################################################################################

def GetTLINK(G, path, dictRouteLinks):

    """
    Return the TLINKS given a list of node tuples.
    """

    lstSource = path[0:len(path) - 1]
    lstTarget = path[1:len(path)]
    lstPath   = zip(lstSource, lstTarget)

    lstLinks = []

    for p in lstPath:
        data  = G.get_edge_data(*p)
        tlink = 0
        for k in data.keys():
            if data[k]['link'] in dictRouteLinks:
                tlink = data[k]['link']
        if tlink == 0:
            cost = data[0]['cost']
            for k in data.keys():
                if data[k]['cost'] <= cost:
                    cost = data[k]['cost']
                    tlink = data[k]['link']
        lstLinks.append(tlink)

    return lstLinks

####################################################################################################

def RidershipAlgorithm():

    """
    The big ridership algorithm!
    """

    try:

        # list for tracking tracking failed routing attempts
        # dictBadData     : alightings that exceed the expected bus load
        # dictMissingLink : a bus stop with a missing tlink (this *should* be resolved before running
        #                   this tool)
        lstBadData     = []
        lstMissingLink = []

        # directed multigraph data structure
        G = CreateDirectedMultiGraph()

        # TLINK segments in each route as specified by Metro
        dictRouteSegments = SubgraphDataLookup()

        # route metrics exported from MetroTool query
        dictRouteMetrics, dictRouteTotals = RouteDataLookup()

        # lookup to extract graph edges by TLINK
        dictAllNodes = NodeLookup(G)

        # for each route...
        for r in dictRouteSegments.keys():

            # generate subgraph for route
            dictRouteLinks, dictRouteNodes, subgraph = CreateSubgraph(G, r, dictRouteSegments)

            # for each direction inbound/outbound...
            for dir in dictRouteMetrics.keys():

                dictStops = dictRouteMetrics[dir][r]
                lstStops  = sorted(dictStops.keys())

                # enumerate total boardings and alightings for the route
                total     = 0
                total_on  = dictRouteTotals[dir][r]['ons']
                total_off = dictRouteTotals[dir][r]['offs']

                # for each stop...
                for i, s in enumerate(lstStops[0:len(lstStops) - 1]):

                    # determine source and target data
                    lstSourceData = dictStops[s]
                    eSource       = lstSourceData[0]
                    ons           = lstSourceData[1]
                    offs          = lstSourceData[2]
                    lstTargetData = dictStops[lstStops[i + 1]]
                    eTarget      = lstTargetData[0]

                    try:

                        source = dictRouteNodes[eSource][0]
                        target = dictRouteNodes[eTarget][0]

                        try:

                            path   = nx.shortest_path(subgraph, source, target, weight='cost')
                            tlinks = GetTLINK(G, path, dictRouteLinks)

                        except nx.NetworkXNoPath:
                            pass

                    except (IndexError, KeyError):

                        # An IndexError will arise when the subgraph does not contain a TLINK indicated
                        # in the MetroTool query (i.e., the route data and the ridership data are from
                        # different service periods). If this occurs, the algorithm is instead applied
                        # to the entire graph.

                        try:

                            dictRouteNodes = dictAllNodes
                            source         = dictRouteNodes[eSource][0]
                            target         = dictRouteNodes[eTarget][0]

                            try:

                                path   = nx.shortest_path(G, source, target, weight='cost')
                                tlinks = GetTLINK(G, path, dictRouteLinks)

                            except nx.NetworkXNoPath:
                                pass

                        except IndexError:

                            # This IndexError will arise when the graph does not contain a TLINK
                            # indicated in the MetroTool query.

                            lstMissingLink.append((r, dir))
                            break

                    # include the source edge and exclude the target edge
                    if eSource not in tlinks:
                        tlinks = [eSource] + tlinks
                    if eTarget in tlinks:
                        tlinks = tlinks[0:len(tlinks) - 1]
                    path_nodes = [dictAllNodes[t] for t in tlinks]

                    adjusted_ons, adjusted_offs = AdjustRidership(ons, offs, total_on, total_off)

                    # apply ridership data to graph
                    if i == 0:
                        total = total + adjusted_ons + adjusted_offs
                        G[dictRouteNodes[eSource][0]][dictRouteNodes[eSource][1]][0]['total'] += total
                        if total < adjusted_offs:
                            lstBadData.append((r, dir))
                            if total_on > total_off:
                                total = total_on
                            else:
                                total = total_off
                            for p in path_nodes[1:len(path_nodes)]:
                                G[p[0]][p[1]][0]['total'] += total
                        else:
                            total = total - adjusted_offs
                            for p in path_nodes[1:len(path_nodes)]:
                                G[p[0]][p[1]][0]['total'] += total
                    else:
                        total = total + adjusted_ons
                        G[dictRouteNodes[eSource][0]][dictRouteNodes[eSource][1]][0]['total'] += total
                        if total < adjusted_offs:
                            lstBadData.append((r, dir))
                            if total_on > total_off:
                                total = total_on
                            else:
                                total = total_off
                            for p in path_nodes[1:len(path_nodes)]:
                                G[p[0]][p[1]][0]['total'] += total
                        else:
                            total = total - adjusted_offs
                            for p in path_nodes[1:len(path_nodes)]:
                                G[p[0]][p[1]][0]['total'] += total

        return (G, lstBadData, lstMissingLink)


    except Exception:
        arcpy.AddError(traceback.format_exc())
        arcpy.AddError('\nError: Unable to complete ridership algorithm.')
        raise SystemExit()

def main():

    G, lstBadData, lstMissingLink = RidershipAlgorithm()

    arcpy.Copy_management(fcStreets, fcOut)
    arcpy.AddField_management(fcOut, 'RIDERS', 'DOUBLE')

    dd = defaultdict(float)
    for edge in G.edges(data=('link', 'total')):
        data = G.get_edge_data(*edge)
        for k in data.keys():
            dd[data[k]['link']] = data[k]['total']

    with arcpy.da.UpdateCursor(fcOut, ['TLINK_ID', 'RIDERS']) as cursor:
        for row in cursor:
            if row[0] in dd.keys():
                riders = dd[row[0]]
            else:
                riders = 0
            cursor.updateRow([row[0], riders])

main()
