# look for arcpy access, otherwise use open source version
# open source version may be faster?
try:
    import imp
    imp.find_module('arcpy')
    from arc_restapi import *
    __opensource__ = False

except ImportError:
    from open_restapi import *
    __opensource__ = True

from rest_utils import *
from . import _strings

__all__ = ['MapServiceLayer',  'ImageService', 'Geocoder', 'FeatureService', 'FeatureLayer', '__opensource__',
           'exportFeatureSet', 'exportReplica', 'exportFeaturesWithAttachments', 'Geometry', 'GeometryCollection',
           'GeocodeService', 'GPService', 'GPTask', 'POST', 'MapService', 'ArcServer', 'Cursor',
           'generate_token', 'mil_to_date', 'date_to_mil', 'guessWKID', 'validate_name'] + \
           ['GeometryService', 'GeometryCollection'] + [d for d in dir(_strings) if not d.startswith('__')]

class Cursor(FeatureSet):
    """Class to handle Cursor object"""
    json = {}
    fieldOrder = []
    field_names = []

    def __init__(self, feature_set, fieldOrder=[]):
        """Cursor object for a feature set
        Required:
            feature_set -- feature set as json or restapi.FeatureSet() object
        Optional:
            fieldOrder -- order of fields for cursor row returns.  To explicitly
                specify and OBJECTID field or Shape (geometry field), you must use
                the field tokens 'OID@' and 'SHAPE@' respectively.
        """
        if isinstance(feature_set, FeatureSet):
            feature_set = feature_set.json

        super(Cursor, self).__init__(feature_set)
        self.fieldOrder = self.__validateOrderBy(fieldOrder)

    @property
    def date_fields(self):
        """gets the names of any date fields within feature set"""
        return [f.name for f in self.fields if f.type == DATE_FIELD]

    @property
    def field_names(self):
        """gets the field names for feature set"""
        names = []
        for f in self.fieldOrder:
            if f == OID_TOKEN and self.OIDFieldName:
                names.append(self.OIDFieldName)
            elif f == SHAPE_TOKEN and self.ShapeFieldName:
                names.append(self.ShapeFieldName)
            else:
                names.append(f)
        return names

    @property
    def OIDFieldName(self):
        """gets the OID field name if it exists in feature set"""
        try:
            return [f.name for f in self.fields if f.type == OID][0]
        except IndexError:
           return None

    @property
    def ShapeFieldName(self):
        """gets the Shape field name if it exists in feature set"""
        try:
            return [f.name for f in self.fields if f.type == SHAPE][0]
        except IndexError:
           return None

    def get_rows(self):
        """returns row objects"""
        for feature in self.features:
            yield self.__createRow(feature, self.spatialReference)

    def rows(self):
        """returns Cursor.rows() as generator"""
        for feature in self.features:
            yield self.__createRow(feature, self.spatialReference).values

    def getRow(self, index):
        """returns row object at index"""
        return [r for r in self.get_rows()][index]

    def __validateOrderBy(self, fields):
        """fixes "fieldOrder" input fields, accepts esri field tokens too ("SHAPE@", "OID@")
        Required:
            fields -- list or comma delimited field list
        """
        if not fields:
            fields = [f.name for f in self.fields]
        if isinstance(fields, basestring):
            fields = fields.split(',')
        for i,f in enumerate(fields):
            if '@' in f:
                fields[i] = f.upper()
            if f == self.ShapeFieldName:
                fields[i] = SHAPE_TOKEN
            if f == self.OIDFieldName:
                fields[i] = OID_TOKEN

        if not fields:
            fields = self.field_names

        return fields

    def __iter__(self):
        """returns Cursor.rows()"""
        return self.rows()

    def __createRow(self, feature, spatialReference):

        cursor = self

        class Row(object):
            """Class to handle Row object"""
            def __init__(self, feature, spatialReference):
                """Row object for Cursor
                Required:
                    feature -- features JSON object
                """
                self.feature = feature
                self.spatialReference = spatialReference

            @property
            def geometry(self):
                """returns a restapi.Geometry() object"""
                if GEOMETRY in self.feature:
                    gd = copy.deepcopy(self.feature.geometry)
                    gd[SPATIAL_REFERENCE] = cursor.json.spatialReference
                    return Geometry(gd)
                return None

            @property
            def oid(self):
                """returns the OID for row"""
                if cursor.OIDFieldName:
                    return self.get(cursor.OIDFieldName)
                return None

            @property
            def values(self):
                """returns values as tuple"""
                # fix date format in milliseconds to datetime.datetime()
                vals = []
                for i, field in enumerate(cursor.fieldOrder):
                    if field in cursor.date_fields:
                        vals.append(mil_to_date(self.feature.attributes[field]))
                    else:
                        if field == OID_TOKEN:
                            vals.append(self.oid)
                        elif field == SHAPE_TOKEN:
                            vals.append(self.geometry)
                        else:
                            vals.append(self.feature.attributes[field])

                return tuple(vals)

            def get(self, field):
                """gets an attribute by field name
                Required:
                    field -- name of field for which to get the value
                """
                return self.feature.attributes.get(field)

            def __getitem__(self, i):
                """allows for getting a field value by index"""
                return self.values[i]

        return Row(feature, spatialReference)

class ArcServer(BaseArcServer):

    def getService(self, name_or_wildcard):
        """method to return Service Object (MapService, FeatureService, GPService, etc).
        This method supports wildcards

        Required:
            name_or_wildcard -- service name or wildcard used to grab service name
                (ex: "moun_webmap_rest/mapserver" or "*moun*mapserver")
        """
        full_path = self.get_service_url(name_or_wildcard)
        if full_path:
            extension = full_path.split('/')[-1]
            if extension == 'MapServer':
                return MapService(full_path, token=self.token)
            elif extension == 'FeatureServer':
                 return FeatureService(full_path, token=self.token)
            elif extension == 'GPServer':
                 return GPService(full_path, token=self.token)
            elif extension == 'ImageServer':
                 return ImageService(full_path, token=self.token)
            elif extension == 'GeocodeServer':
                return Geocoder(full_path, token=self.token)
            else:
                raise NotImplementedError('restapi does not support "{}" services!')

class MapServiceLayer(BaseMapServiceLayer):
    """Class to handle advanced layer properties"""

    def cursor(self, fields='*', where='1=1', add_params={}, records=None, get_all=False):
        """Run Cursor on layer, helper method that calls Cursor Object"""
        cur_fields = self.fix_fields(fields)

        fs = self.query(cur_fields, where, add_params, records, get_all)
        return Cursor(fs, fields)

    def layer_to_fc(self, out_fc, fields='*', where='1=1', records=None, params={}, get_all=False, sr=None):
        """Method to export a feature class from a service layer

        Required:
            out_fc -- full path to output feature class

        Optional:
            where -- optional where clause
            params -- dictionary of parameters for query
            fields -- list of fields for fc. If none specified, all fields are returned.
                Supports fields in list [] or comma separated string "field1,field2,.."
            records -- number of records to return. Default is none, will return maxRecordCount
            get_all -- option to get all records.  If true, will recursively query REST endpoint
                until all records have been gathered. Default is False.
            sr -- output spatial refrence (WKID)
        """
        if self.type == 'Feature Layer':
            if not fields:
                fields = '*'
            if fields == '*':
                _fields = self.fields
            else:
                if isinstance(fields, basestring):
                    fields = fields.split(',')
                _fields = [f for f in self.fields if f.name in fields]

            # filter fields for cusor object
            cur_fields = []
            for fld in _fields:
                if fld.type not in [OID] + SKIP_FIELDS.keys():
                    if not any(['shape_' in fld.name.lower(),
                                'shape.' in fld.name.lower(),
                                '(shape)' in fld.name.lower(),
                                'objectid' in fld.name.lower(),
                                fld.name.lower() == 'fid']):
                        cur_fields.append(fld.name)

            # make new feature class
            if not sr:
                sr = self.getSR()
            else:
                params['outSR'] = sr

            # do query to get feature set
            fs = self.query(cur_fields, where, params, records, get_all)

            return exportFeatureSet(out_fc, fs)

        else:
            print('Layer: "{}" is not a Feature Layer!'.format(self.name))

    def clip(self, poly, output, fields='*', out_sr='', where='', envelope=False):
        """Method for spatial Query, exports geometry that intersect polygon or
        envelope features.

        Required:
            poly -- polygon (or other) features used for spatial query
            output -- full path to output feature class

        Optional:
             fields -- list of fields for fc. If none specified, all fields are returned.
                Supports fields in list [] or comma separated string "field1,field2,.."
            out_sr -- output spatial refrence (WKID)
            where -- optional where clause
            envelope -- if true, the polygon features bounding box will be used.  This option
                can be used if the feature has many vertices or to check against the full extent
                of the feature class
        """
        if isinstance(poly, Geometry):
            in_geom = poly
        else:
            in_geom = Geometry(poly)
        sr = in_geom.spatialReference
        if envelope:
            geojson = in_geom.envelopeAsJSON()
            geometryType = ESRI_ENVELOPE
        else:
            geojson = in_geom.dumps()
            geometryType = in_geom.geometryType

        if not out_sr:
            out_sr = sr

        d = {GEOMETRY_TYPE: geometryType,
             'returnGeometry': 'true',
             'geometry': geojson,
             'inSR' : sr,
             'outSR': out_sr}

        return self.layer_to_fc(output, fields, where, params=d, get_all=True, sr=out_sr)

class MapService(BaseMapService):

    def layer(self, name_or_id):
        """Method to return a layer object with advanced properties by name

        Required:
            name -- layer name (supports wildcard syntax*) or id (must be of type <int>)
        """
        if isinstance(name_or_id, int):
            # reference by id directly
            return MapServiceLayer('/'.join([self.url, str(name_or_id)]), token=self.token)

        layer_path = get_layer_url(self.url, name_or_id, self.token)
        if layer_path:
            return MapServiceLayer(layer_path, token=self.token)
        else:
            print('Layer "{0}" not found!'.format(name_or_id))

    def cursor(self, layer_name, fields='*', where='1=1', records=None, add_params={}, get_all=False):
        """Cusor object to handle queries to rest endpoints

        Required:
           layer_name -- name of layer in map service

        Optional:
            fields -- option to limit fields returned.  All are returned by default
            where -- where clause for cursor
            records -- number of records to return (within bounds of max record count)
            token --
            add_params -- option to add additional search parameters
            get_all -- option to get all records in layer.  This option may be time consuming
                because the ArcGIS REST API uses default maxRecordCount of 1000, so queries
                must be performed in chunks to get all records
        """
        lyr = get_layer_url(self.url, layer_name, self.token)
        return Cursor(lyr, fields, where, records, self.token, add_params, get_all)

    def layer_to_fc(self, layer_name,  out_fc, fields='*', where='1=1',
                    records=None, params={}, get_all=False, sr=None):
        """Method to export a feature class from a service layer

        Required:
            layer_name -- name of map service layer to export to fc
            out_fc -- full path to output feature class

        Optional:
            where -- optional where clause
            params -- dictionary of parameters for query
            fields -- list of fields for fc. If none specified, all fields are returned.
                Supports fields in list [] or comma separated string "field1,field2,.."
            records -- number of records to return. Default is none, will return maxRecordCount
            get_all -- option to get all records.  If true, will recursively query REST endpoint
                until all records have been gathered. Default is False.
            sr -- output spatial refrence (WKID)
        """
        lyr = self.layer(layer_name)
        lyr.layer_to_fc(out_fc, fields, where,records, params, get_all, sr)

    def layer_to_kmz(self, layer_name, out_kmz='', flds='*', where='1=1', params={}):
        """Method to create kmz from query

        Required:
            layer_name -- name of map service layer to export to fc

        Optional:
            out_kmz -- output kmz file path, if none specified will be saved on Desktop
            flds -- list of fields for fc. If none specified, all fields are returned.
                Supports fields in list [] or comma separated string "field1,field2,.."
            where -- optional where clause
            params -- dictionary of parameters for query
        """
        lyr = self.layer(layer_name)
        lyr.layer_to_kmz(flds, where, params, kmz=out_kmz)

    def clip(self, layer_name, poly, output, fields='*', out_sr='', where='', envelope=False):
        """Method for spatial Query, exports geometry that intersect polygon or
        envelope features.

        Required:
            layer_name -- name of map service layer to export to fc
            poly -- polygon (or other) features used for spatial query
            output -- full path to output feature class

        Optional:
             fields -- list of fields for fc. If none specified, all fields are returned.
                Supports fields in list [] or comma separated string "field1,field2,.."
            sr -- output spatial refrence (WKID)
            where -- optional where clause
            envelope -- if true, the polygon features bounding box will be used.  This option
                can be used if the feature has many vertices or to check against the full extent
                of the feature class
        """
        lyr = self.layer(layer_name)
        return lyr.clip(poly, output, fields, out_sr, where, envelope)

class FeatureService(MapService):
    """class to handle Feature Service

    Required:
        url -- image service url

    Optional (below params only required if security is enabled):
        usr -- username credentials for ArcGIS Server
        pw -- password credentials for ArcGIS Server
        token -- token to handle security (alternative to usr and pw)
        proxy -- option to use proxy page to handle security, need to provide
            full path to proxy url.
    """

    @property
    def replicas(self):
        """returns a list of replica objects"""
        if self.syncEnabled:
            reps = POST(self.url + '/replicas', cookies=self._cookie)
            return [namedTuple('Replica', r) for r in reps]
        else:
            return []

    def layer(self, name_or_id):
        """Method to return a layer object with advanced properties by name

        Required:
            name -- layer name (supports wildcard syntax*) or layer id (int)
        """
        if isinstance(name_or_id, int):
            # reference by id directly
            return FeatureLayer('/'.join([self.url, str(name_or_id)]), token=self.token)

        layer_path = self.get_layer_url(name_or_id)
        if layer_path:
            return FeatureLayer(layer_path, token=self.token)
        else:
            print('Layer "{0}" not found!'.format(name_or_id))

    def layer_to_kmz(self, layer_name, out_kmz='', flds='*', where='1=1', params={}):
        """Method to create kmz from query

        Required:
            layer_name -- name of map service layer to export to fc

        Optional:
            out_kmz -- output kmz file path, if none specified will be saved on Desktop
            flds -- list of fields for fc. If none specified, all fields are returned.
                Supports fields in list [] or comma separated string "field1,field2,.."
            where -- optional where clause
            params -- dictionary of parameters for query
        """
        lyr = self.layer(layer_name)
        lyr.layer_to_kmz(flds, where, params, kmz=out_kmz)

    def createReplica(self, layers, replicaName, geometry='', geometryType='', inSR='', replicaSR='', **kwargs):
        """query attachments, returns a JSON object

        Required:
            layers -- list of layers to create replicas for (valid inputs below)
            replicaName -- name of replica

        Optional:
            geometry -- optional geometry to query features
            geometryType -- type of geometry
            inSR -- input spatial reference for geometry
            replicaSR -- output spatial reference for replica data
            **kwargs -- optional keyword arguments for createReplica request
        """
        if hasattr(self, 'syncEnabled') and not self.syncEnabled:
            raise NotImplementedError('FeatureService "{}" does not support Sync!'.format(self.url))

        # validate layers
        if isinstance(layers, basestring):
            layers = [l.strip() for l in layers.split(',')]

        elif not isinstance(layers, (list, tuple)):
            layers = [layers]

        if all(map(lambda x: isinstance(x, int), layers)):
            layers = ','.join(map(str, layers))

        elif all(map(lambda x: isinstance(x, basestring), layers)):
            layers = ','.join(map(str, filter(lambda x: x is not None,
                                [s.id for s in self.layers if s.name.lower()
                                 in [l.lower() for l in layers]])))

        if not geometry and not geometryType:
            ext = self.initialExtent
            inSR = self.initialExtent.spatialReference
            geometry= ','.join(map(str, [ext.xmin,ext.ymin,ext.xmax,ext.ymax]))
            geometryType = ESRI_ENVELOPE
            inSR = self.spatialReference
            useGeometry = False
        else:
            useGeometry = True
            if isinstance(geometry, dict) and SPATIAL_REFERENCE in geometry and not inSR:
                inSR = geometry[SPATIAL_REFERENCE]


        if not replicaSR:
            replicaSR = self.spatialReference

        validated = layers.split(',')
        options = {'replicaName': replicaName,
                   'layers': layers,
                   'layerQueries': '',
                   GEOMETRY: geometry,
                   GEOMETRY_TYPE: geometryType,
                   'inSR': inSR,
                   'replicaSR':	replicaSR,
                   'transportType':	'esriTransportTypeUrl',
                   'returnAttachments':	'true',
                   'returnAttachmentsDataByUrl': 'true',
                   'async':	'false',
                   'f': 'pjson',
                   'dataFormat': 'json',
                   'replicaOptions': '',
                   }

        for k,v in kwargs.iteritems():
            options[k] = v
            if k == 'layerQueries':
                if options[k]:
                    if isinstance(options[k], basestring):
                        options[k] = json.loads(options[k])
                    for key in options[k].keys():
                        options[k][key]['useGeometry'] = useGeometry
                        options[k] = json.dumps(options[k])

        if self.syncCapabilities.supportsPerReplicaSync:
            options['syncModel'] = 'perReplica'
        else:
            options['syncModel'] = 'perLayer'

        if options['async'] in ('true', True) and self.syncCapabilities.supportsAsync:
            st = POST(self.url + '/createReplica', options, cookies=self._cookie)
            while 'statusUrl' not in st:
                time.sleep(1)
        else:
            options['async'] = 'false'
            st = POST(self.url + '/createReplica', options, cookies=self._cookie)

        RequestError(st)
        js = POST(st['URL'] if 'URL' in st else st['statusUrl'], cookies=self._cookie)
        RequestError(js)

        if not replicaSR:
            replicaSR = self.spatialReference

        repLayers = []
        for i,l in enumerate(js['layers']):
            l['layerURL'] = '/'.join([self.url, validated[i]])
            layer_ob = FeatureLayer(l['layerURL'], token=self.token)
            l['fields'] = layer_ob.fields
            l['name'] = layer_ob.name
            l['geometryType'] = layer_ob.geometryType
            l[SPATIAL_REFERENCE] = replicaSR
            if not 'attachments' in l:
                l['attachments'] = []
            repLayers.append(namedTuple('ReplicaLayer', l))

        rep_dict = js
        rep_dict['layers'] = repLayers
        return namedTuple('Replica', rep_dict)

    def replicaInfo(self, replicaID):
        """get replica information

        Required:
            replicaID -- ID of replica
        """
        query_url = self.url + '/replicas/{}'.format(replicaID)
        return namedTuple('ReplicaInfo', POST(query_url, cookies=self._cookie))

    def syncReplica(self, replicaID, **kwargs):
        """synchronize a replica.  Must be called to sync edits before a fresh replica
        can be obtained next time createReplica is called.  Replicas are snapshots in
        time of the first time the user creates a replica, and will not be reloaded
        until synchronization has occured.  A new version is created for each subsequent
        replica, but it is cached data.

        It is also recommended to unregister a replica
        AFTER sync has occured.  Alternatively, setting the "closeReplica" keyword
        argument to True will unregister the replica after sync.

        More info can be found here:
            http://server.arcgis.com/en/server/latest/publish-services/windows/prepare-data-for-offline-use.htm

        and here for key word argument parameters:
            http://resources.arcgis.com/en/help/arcgis-rest-api/index.html#/Synchronize_Replica/02r3000000vv000000/

        Required:
            replicaID -- ID of replica
        """
        query_url = self.url + '/synchronizeReplica'
        params = {'replicaID': replicaID}

        for k,v in kwargs.iteritems():
            params[k] = v

        return POST(query_url, params, cookies=self._cookie)


    def unRegisterReplica(self, replicaID):
        """unregisters a replica on the feature service

        Required:
            replicaID -- the ID of the replica registered with the service
        """
        query_url = self.url + '/unRegisterReplica'
        params = {'replicaID': replicaID}
        return POST(query_url, params, cookies=self._cookie)

class FeatureLayer(MapServiceLayer):
    """class to handle Feature Service Layer

        Required:
            url -- image service url

        Optional (below params only required if security is enabled):
            usr -- username credentials for ArcGIS Server
            pw -- password credentials for ArcGIS Server
            token -- token to handle security (alternative to usr and pw)
            proxy -- option to use proxy page to handle security, need to provide
                full path to proxy url.
    """

    def addFeatures(self, features, gdbVersion='', rollbackOnFailure=True):
        """add new features to feature service layer

        features -- esri JSON representation of features

        ex:
        adds = [{"geometry":
                     {"x":-10350208.415443439,
                      "y":5663994.806146532,
                      "spatialReference":
                          {"wkid":102100}},
                 "attributes":
                     {"Utility_Type":2,"Five_Yr_Plan":"No","Rating":None,"Inspection_Date":1429885595000}}]
        """
        add_url = self.url + '/addFeatures'
        params = {'features': json.dumps(features) if isinstance(features, list) else features,
                  'gdbVersion': gdbVersion,
                  'rollbackOnFailure': str(rollbackOnFailure).lower(),
                  'f': 'pjson'}

        # update features
        result = EditResult(POST(add_url, params, cookies=self._cookie))
        result.summary()
        return result

    def updateFeatures(self, features, gdbVersion='', rollbackOnFailure=True):
        """update features in feature service layer

        Required:
            features -- features to be updated (JSON)

        Optional:
            gdbVersion -- geodatabase version to apply edits
            rollbackOnFailure -- specify if the edits should be applied only if all submitted edits succeed

        # example syntax
        updates = [{"geometry":
                {"x":-10350208.415443439,
                 "y":5663994.806146532,
                 "spatialReference":
                     {"wkid":102100}},
            "attributes":
                {"Five_Yr_Plan":"Yes","Rating":90,"OBJECTID":1}}] #only fields that were changed!
        """
        update_url = self.url + '/updateFeatures'
        params = {'features': json.dumps(features),
                  'gdbVersion': gdbVersion,
                  'rollbackOnFailure': rollbackOnFailure,
                  'f': 'json'}

        # update features
        result = EditResult(POST(update_url, params, cookies=self._cookie))
        result.summary()
        return result

    def deleteFeatures(self, oids='', where='', geometry='', geometryType='',
                       spatialRel='', inSR='', gdbVersion='', rollbackOnFailure=True):
        """deletes features based on list of OIDs

        Optional:
            oids -- list of oids or comma separated values
            where -- where clause for features to be deleted.  All selected features will be deleted
            geometry -- geometry JSON object used to delete features.
            geometryType -- type of geometry
            spatialRel -- spatial relationship.  Default is "esriSpatialRelationshipIntersects"
            inSR -- input spatial reference for geometry
            gdbVersion -- geodatabase version to apply edits
            rollbackOnFailure -- specify if the edits should be applied only if all submitted edits succeed

        oids format example:
            oids = [1, 2, 3] # list
            oids = "1, 2, 4" # as string
        """
        if not geometryType:
            geometryType = 'esriGeometryEnvelope'
        if not spatialRel:
            spatialRel = 'esriSpatialRelIntersects'

        del_url = self.url + '/deleteFeatures'
        if isinstance(oids, (list, tuple)):
            oids = ', '.join(map(str, oids))
        params = {'objectIds': oids,
                  'where': where,
                  GEOMETRY: geometry,
                  GEOMETRY_TYPE: geometryType,
                  'spatialRel': spatialRel,
                  'gdbVersion': gdbVersion,
                  'rollbackOnFailure': rollbackOnFailure,
                  'f': 'json'}

        # delete features
        result = EditResult(POST(del_url, params, cookies=self._cookie))
        result.summary()
        return result

    def applyEdits(self, adds='', updates='', deletes='', gdbVersion='', rollbackOnFailure=True):
        """apply edits on a feature service layer

        Optional:
            adds -- features to add (JSON)
            updates -- features to be updated (JSON)
            deletes -- oids to be deleted (list, tuple, or comma separated string)
            gdbVersion -- geodatabase version to apply edits
            rollbackOnFailure -- specify if the edits should be applied only if all submitted edits succeed
        """
        # TO DO
        pass

    def addAttachment(self, oid, attachment, content_type='', gdbVersion=''):
        """add an attachment to a feature service layer

        Required:
            oid -- OBJECT ID of feature in which to add attachment
            attachment -- path to attachment

        Optional:
            content_type -- html media type for "content_type" header.  If nothing provided,
                will use a best guess based on file extension (using mimetypes)
            gdbVersion -- geodatabase version for attachment

            valid content types can be found here @:
                http://en.wikipedia.org/wiki/Internet_media_type
        """
        if self.hasAttachments:

            # use mimetypes to guess "content_type"
            if not content_type:
                import mimetypes
                known = mimetypes.types_map
                common = mimetypes.common_types
                ext = os.path.splitext(attachment)[-1].lower()
                if ext in known:
                    content_type = known[ext]
                elif ext in common:
                    content_type = common[ext]

            # make post request
            att_url = '{}/{}/addAttachment'.format(self.url, oid)
            files = {'attachment': (os.path.basename(attachment), open(attachment, 'rb'), content_type)}
            params = {'f': 'json'}
            if gdbVersion:
                params['gdbVersion'] = gdbVersion
            r = requests.post(att_url, params, files=files, cookies=self._cookie, verify=False).json()
            if 'addAttachmentResult' in r:
                print(r['addAttachmentResult'])
            return r

        else:
            raise NotImplementedError('FeatureLayer "{}" does not support attachments!'.format(self.name))

    def calculate(self, exp, where='1=1', sqlFormat='standard'):
        """calculate a field in a Feature Layer

        Required:
            exp -- expression as JSON [{"field": "Street", "value": "Main St"},..]

        Optional:
            where -- where clause for field calculator
            sqlFormat -- SQL format for expression (standard|native)

        Example expressions as JSON:
            exp = [{"field" : "Quality", "value" : 3}]
            exp =[{"field" : "A", "sqlExpression" : "B*3"}]
        """
        if hasattr(self, 'supportsCalculate') and self.supportsCalculate:
            calc_url = self.url + '/calculate'
            p = {'returnIdsOnly':'true',
                'returnGeometry': 'false',
                'outFields': '',
                'calcExpression': json.dumps(exp),
                'sqlFormat': sqlFormat}

            return POST(calc_url, where=where, add_params=p, cookies=self._cookie)

        else:
            raise NotImplementedError('FeatureLayer "{}" does not support field calculations!'.format(self.name))

class GeometryService(RESTEndpoint):
    linear_units = sorted(LINEAR_UNITS.keys())

    @staticmethod
    def getLinearUnitWKID(unit_name):
        """gets a well known ID from a unit name

        Required:
            unit_name -- name of unit to fetch WKID for.  It is safe to use this as
                a filter to ensure a valid WKID is extracted.  if a WKID is passed in,
                that same value is returned.  This argument is expecting a string from
                linear_units list.  Valid options can be viewed with GeometryService.linear_units
        """
        if isinstance(unit_name, int) or unicode(unit_name).isdigit():
            return int(unit_name)

        for k,v in LINEAR_UNITS.iteritems():
            if k.lower() == unit_name.lower():
                return int(v[WKID])

    @staticmethod
    def validateGeometries(geometries, use_envelopes=False):
        """

        """
        cleanGeometry = {}
        geometryType = ''
        geoms = []
        if isinstance(geometries, basestring):
            if '{' in geometries:
                geometries = json.loads(geometries)

        # there is just a single geometry
        if isinstance(geometries, Geometry):
            geometries =  [geometries]


        # it is json it may be correct, but iterate through and validate anyways
        if isinstance(geometries, dict):
            if 'geometries' in geometries:
                theGeoms = geometries['geometries']
                if isinstance(theGeoms, list):
                    for geom in theGeoms:
                        if isinstance(geom, Geometry):
                            if use_envelopes:
                                geoms.append(geom.envelopeAsJSON())
                            else:
                                geoms.append(geom.JSON)
                        elif isinstance(geom, dict):
                            geoms.append(geom)

            else:
                geoms.append(geometries)

            if GEOMETRY_TYPE in geometries:
                geometryType = geometries[GEOMETRY_TYPE]


        # we just have a list of Geometry Objects, dicts or bounding boxes
        if isinstance(geometries, list):
            for geom in geometries:
                if isinstance(geom, Geometry):
                    if use_envelopes:
                        geoms.append(geom.envelopeAsJSON())
                    else:
                        geoms.append(geom.JSON)

                    if not geometryType:
                        geometryType = geom.geometryType if not use_envelopes else ESRI_ENVELOPE

                elif isinstance(geom, dict):
                    geoms.append(geom)

        # form json
        if not geometryType and len(geoms):
            if 'x' in geoms[0]:
                geometryType = ESRI_POINT
            elif 'points' in geoms[0]:
                geometryType = ESRI_MULTIPOINT
            elif 'paths' in geoms[0]:
                geometryType = ESRI_POLYLINE
            elif 'rings' in geoms[0]:
                geometryType = ESRI_POLYGON
            else:
                geometryType = ESRI_ENVELOPE

        return {GEOMETRY_TYPE: geometryType, 'geometries': geoms}

    @staticmethod
    def returnGeometry(in_json, wkid=None):
        """passthrough helper method to return a single Geometry or GeometryCollection
        based on JSON response.

        Required:
            in_json -- input JSON response

        Optional:
            wkid -- well known ID for spatial reference, required to output valid Geometry objects
        """
        if isinstance(in_json, dict) and 'geometries' in in_json:
            if wkid:
                for geometry in in_json['geometries']:
                    geometry[SPATIAL_REFERENCE] = {WKID: wkid}
                gc = GeometryCollection(in_json)

                # if only one geometry, return it as a Geometry() object otherwise as GeometryCollection()
                if len(gc) == 1:
                    return gc[0]
                else:
                    return gc

            else:
                return in_json

    def buffer(self, geometries, inSR, distances, unit='', outSR='', use_envelopes=False, **kwargs):
        """buffer a single geoemetry or multiple

        Required:
            geometries -- array of geometries to be buffered. The spatial reference of the geometries
                is specified by inSR. The structure of each geometry in the array is the same as the
                structure of the JSON geometry objects returned by the ArcGIS REST API.

            inSR -- wkid for input geometry

            distances -- the distances that each of the input geometries is buffered. The distance units
                are specified by unit.

        Optional:

            use_envelopes -- not a valid option in ArcGIS REST API, this is an extra argument that will
                convert the geometries to bounding box envelopes ONLY IF they are restapi.Geometry objects,
                otherwise this parameter is ignored.


        """
        buff_url = self.url + '/buffer'

        params = {'f': 'pjson',
                  'geometries': self.validateGeometries(geometries),
                  'inSR': inSR,
                  'distances': distances,
                  'unit': self.getLinearUnitWKID(unit),
                  'outSR': outSR,
                  'unionResults': 'true',
                  'geodesic': 'false',
                  'outSR': '',
                  'bufferSR': ''
                }

        # add kwargs
        for k,v in kwargs:
            if k not in params:
                params[k] = v

        # perform operation
        return self.returnGeometry(POST(buff_url, params, token=self.token))


    def findTransformations(self, inSR, outSR, extentOfInterest='', numOfResults=1):
        """finds the most applicable transformation based on inSR and outSR

        Required:
            inSR -- input Spatial Reference (wkid)
            outSR -- output Spatial Reference (wkid)

        Optional:
            extentOfInterest --e bounding box of the area of interest specified as a
                JSON envelope. If provided, the extent of interest is used to return
                the most applicable geographic transformations for the area. If a spatial
                reference is not included in the JSON envelope, the inSR is used for the
                envelope.

            numOfResults -- The number of geographic transformations to return. The
                default value is 1. If numOfResults has a value of -1, all applicable
                transformations are returned.

        return looks like this:
            [
              {
                "wkid": 15851,
                "latestWkid": 15851,
                "name": "NAD_1927_To_WGS_1984_79_CONUS"
              },
              {
                "wkid": 8072,
                "latestWkid": 1172,
                "name": "NAD_1927_To_WGS_1984_3"
              },
              {
                "geoTransforms": [
                  {
                    "wkid": 108001,
                    "latestWkid": 1241,
                    "transformForward": true,
                    "name": "NAD_1927_To_NAD_1983_NADCON"
                  },
                  {
                    "wkid": 108190,
                    "latestWkid": 108190,
                    "transformForward": false,
                    "name": "WGS_1984_(ITRF00)_To_NAD_1983"
                  }
                ]
              }
            ]
        """
        params = {'inSR': inSR,
                  'outSR': outSR,
                  'extentOfInterest': extentOfInterest,
                  'numOfResults': numOfResults
                }

        res = POST(self.url + '/findTransformations', params, token=self.token)
        if int(numOfResults) == 1:
            return res[0]
        else:
            return res


    def project(self, geometries, inSR, outSR, transformation='', transformForward='false'):
        """project a single or group of geometries

        Required:
            geometries --
            inSR --
            outSR --

        Optional:
            transformation --
            trasnformForward --
        """
        params = {'geometries': validateGeometries(geometries),
                  'inSR': inSR,
                  'outSR': outSR,
                  'transformation': transformation,
                  'transformForward': transformForward
                }

        return POST(self.url + '/project', params, token=self.token)

    def __repr__(self):
        return '<restapi.GeometryService>'