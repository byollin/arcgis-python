'''-------------------------------------------------------------------------------------------------
    Name:       CreateSpiderArcGIS10X
    Purpose:    Adapted from "Spider_Create_10_new.py" for use in ArcGIS10X. Creates lines (edges)
                between an origin points feature layer (nodes) and a destination points feature
                layer (nodes). For each origin point, draws a line connecting it to its respective
                destination indicated by a 'link' field. Adds additional fields to the out feature
                class as specified by the user.

    Revisions:
    Version     Date          Author        Description
    --------    ----------    ----------    ----------
    1.0         5/2/2016      B. Yollin     1. Initial commit
    1.1         5/4/2016      B. Yollin     2. Parameterized script
    1.2         5/9/2016      B. Yollin     3. Optimized script
    1.3         5/11/2016     B. Yollin     4. Code versioning is now maintained on GitLab

    System Requirements:
        - ArcGIS 10.1, 10.2, or 10.3.
        - Python 2.* (.2 to .8) installed with ArcGIS. This must be the default Python version for
          the user.
        - All modules used are installed along with ArcGIS 10.1, 10.2 and 10.3.

    Notes:

    Calls:
        N/A

    Called By:
        ArcGIS Script tool object or N/A

    Parameters:

            Display Name                          Data Type        Type        Direction MultiValue
----------------------------------------------------------------------------------------------------
#  argv[0]  Origin Point Feature Layer            Feature Layer    Required    Input     No
#  argv[1]  Origin Link Field                     Field            Required    Input     No
#  argv[2]  Destination Point Feature Layer       Feature Layer    Required    Input     No
#  argv[3]  Destination Link Field                Field            Required    Input     No
#  argv[4]  Output Polyline Feature Class         Feature Class    Required    Output    No
#  argv[5]  Additional Origin Fields              Fields           Required    Output    Yes
#  argv[6]  Additional Destination Fields         Fields           Required    Output    Yes

-------------------------------------------------------------------------------------------------'''

# import required modules
import os
import sys
import arcpy

# get parameters as text from ArcGIS toolbox input
fcOrigin   = arcpy.GetParameterAsText(0)
fldOrigin  = arcpy.GetParameterAsText(1)
fcDest     = arcpy.GetParameterAsText(2)
fldDest    = arcpy.GetParameterAsText(3)
fcOut      = arcpy.GetParameterAsText(4)
fldsOrigin = arcpy.GetParameterAsText(5)
fldsDest   = arcpy.GetParameterAsText(6)

# create list of additional fields from parameter string
# if string is empty, create an empty list
fldsOrigin = [] if len(fldsOrigin) == 0 else fldsOrigin.split(';')
fldsDest   = [] if len(fldsDest) == 0 else fldsDest.split(';')

####################################################################################################
# BUILD ORIGIN/DESTINATION NODE LIST OF TUPLES FROM ORIGIN/DESTINATION FEATURE LAYERS

def ValuesList(fcIn, fldLink, fldsSource, strFC = 'ORIGIN'):

    fields   = ['OID@', 'SHAPE@XY', fldLink] + fldsSource # add additional fields
    lstTrips = []

    with arcpy.da.SearchCursor(fcIn, fields) as cursor:
        try:
            for row in cursor:

                X = row[1][0]
                Y = row[1][1]

                # only add nodes if x/y values are not null
                if X is not None and Y is not None:

                    # [('OID@', ('SHAPE@XY'), fldLink, fldVal1, fldVal2, ..., fldValn)]
                    lstTrips.append(row)

            if not lstTrips:
                arcpy.AddError('Error: Valid ' + strFC + ' values could not be identified. This \
                               may be because records were selected with \'Not a Number\' \
                               coordinate values. Common for \'unmatched records\' in a geocoded \
                               address database.')
                raise SystemExit()
            else:
                lstTrips = sorted(lstTrips, key = lambda link: link[2]) # sort by link field
                arcpy.AddMessage(strFC + ' coordinates and key values added to ' + strFC + ' list.')
                return lstTrips
        except:
            arcpy.AddWarning(arcpy.GetMessages())
            arcpy.AddError('Error: Problem encountered creating ' + strFC + ' coordinate-key list.')
            arcpy.AddError('\nContact Seattle IT SDOT GIS group.')
            raise SystemExit()

####################################################################################################
# ADD ADDITIONAL FILEDS TO OUTPUT FEATURE CLASS

def AddFields(fcTarget, fcSource, fldsSource, strPrefix = 'ORG'):

    try:
        lstFields = []

        if fldsSource is not ['']:

            # get fields objects
            fldsSource = filter(lambda f: f.name in fldsSource, arcpy.ListFields(fcSource))

            for field in fldsSource:
                strNewField = (strPrefix + '_' + field.name)[0:10] # truncate string
                lstFields.append(strNewField)
                arcpy.AddField_management(fcTarget, strNewField, field.type, field.precision,
                                          field.scale, field.length, field.aliasName)
            return lstFields # return list of new field names
            
    except:
        arcpy.AddWarning(arcpy.GetMessages())
        arcpy.AddError('Error: Problem encountered adding fields to output feature class.')
        arcpy.AddError('\nContact Seattle IT SDOT GIS group.')
        raise SystemExit()

####################################################################################################
# ADD POLYLINES TO OUTPUT FEATURE CLASS AND POPULATE OUTPUT FEATURE CLASS FIELDS

def MakeSpiderFromPoints(fcOrigin, fcDest, fcOut):

    descOrigin  = arcpy.Describe(fcOrigin)
    descDest    = arcpy.Describe(fcDest)
    shpOrigin   = descOrigin.ShapeType
    shpDest     = descDest.ShapeType
    srOrigin    = descOrigin.SpatialReference
    srDest      = descDest.SpatialReference
    strSrOrigin = descOrigin.SpatialReference.Type
    strSrDest   = descDest.SpatialReference.Type

    # some preliminary error checking
    arcpy.AddMessage('Start Process Spider...')
    if shpOrigin == 'Point' and shpDest == 'Point':
        if strSrOrigin == 'Unknown' or strSrDest == 'Unknown':
            arcpy.AddError('Error: Undefined projection in origin or destination feature class.')
            raise SystemExit()
        if strSrOrigin != strSrDest:
            arcpy.AddError('Error: The origin and destination feature classes must have the same \
                           projection.')
            raise SystemExit()
    else:
        arcpy.AddError('Error: Both feature classes must be points.')
        raise SystemExit()

    # generate list of origin and destination nodes
    lstOrigin = ValuesList(fcOrigin, fldOrigin, fldsOrigin)
    lstDest   = ValuesList(fcDest, fldDest, fldsDest, strFC = 'DESTINATION')

    try:

        pathDir = os.path.dirname(fcOut)
        pathOut = os.path.basename(fcOut)
        
        # create out feature class
        arcpy.CreateFeatureclass_management(pathDir, pathOut, "POLYLINE", "''", "DISABLED",
                                            "DISABLED", srOrigin, "", "0", "0", "0")
                                            
        arcpy.AddMessage('Polyline feature class instantiated.')

        arcpy.AddField_management(fcOut, "ORG_OID", 'LONG', "", "", "", "", "", "", "")
        arcpy.AddField_management(fcOut, "DES_OID", 'LONG', "", "", "", "", "", "", "")

        # add addtional fields to out feature class
        lstOriginField = AddFields(fcOut, fcOrigin, fldsOrigin)
        lstDestField   = AddFields(fcOut, fcDest, fldsDest, strPrefix = 'DES')
        
        arcpy.AddMessage('Polyline feature class fields added to schema.')

    except:

        arcpy.AddWarning(arcpy.GetMessages())
        arcpy.AddError('Error: Problem encountered creating feature class.')
        arcpy.AddError('\nContact Seattle IT SDOT GIS group.')
        raise SystemExit()
    
    arcpy.AddMessage('Constructing polylines...')

    fields = ['SHAPE@', 'ORG_OID', 'DES_OID'] + lstOriginField + lstDestField

    cursor  = arcpy.da.InsertCursor(fcOut, fields)
    arrLine = arcpy.CreateObject("Array")
    pntXY   = arcpy.CreateObject("Point")

    # setup up for progress bar
    intRealMax  = len(lstDest)
    intMax      = 10 if intRealMax < 5 else int(round(len(lstDest), -1))
    intInterval = int(intMax/10)

    try:

        arcpy.SetProgressor('step', 'Progress: 0 out of {0}'.format(intRealMax),0, intMax, intInterval)

        for idx, tupDest in enumerate(lstDest):

            # for the current destination, find origins with the same link field value
            idCurr          = tupDest[2]
            lstOriginSubset = filter(lambda tupTripID: tupTripID[2] == idCurr, lstOrigin)

            if lstOriginSubset:

                for tupOrigin in lstOriginSubset:

                    # origin x and y
                    pntXY.X = tupOrigin[1][0]
                    pntXY.Y = tupOrigin[1][1]
                    arrLine.add(pntXY)
                    # destination x and y
                    pntXY.X = tupDest[1][0]
                    pntXY.Y = tupDest[1][1]
                    arrLine.add(pntXY)
                    # insert row
                    geomLine = arcpy.Geometry('Polyline', arrLine, srOrigin)

                    if geomLine.length != 0: # insert row if polyline length is not 0
                        cursor.insertRow((geomLine, tupOrigin[0], tupDest[0]) + tupOrigin[3:len(tupOrigin)] + tupDest[3:len(tupDest)])
                    else:
                        pass

                    arrLine.removeAll()

            # update progress bar
            if(idx % intInterval) == 0:
                arcpy.SetProgressorPosition(idx)
                arcpy.SetProgressorLabel('Progress: {0} out of {1}'.format(idx, intRealMax))

        arcpy.SetProgressorPosition(intMax)
        del cursor
        arcpy.AddMessage('Constructed polylines successfully!')

        # switch back to default progress bar
        arcpy.SetProgressor('default')

    except:
    
        arcpy.AddWarning(arcpy.GetMessages())
        arcpy.AddError('Error: Unable to construct polyline.')
        arcpy.AddError('\nContact Seattle IT SDOT GIS group.')
        raise SystemExit()

MakeSpiderFromPoints(fcOrigin, fcDest, fcOut)
