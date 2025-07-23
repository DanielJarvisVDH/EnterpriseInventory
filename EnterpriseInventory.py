# Created by Daniel Jarvis -  5/1/2025
#
# This script must be stored on a secure server, and run from there.

import socket
from arcgis.gis import GIS
from arcgis.gis.server import Server
import arcpy
import requests
import os
from pathlib import Path
import json

server_name = socket.gethostname()

# Path to DB where your inventory tables are stored
inventoryDatabase = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde"
# ArcGIS Online Table
agoInventoryTable = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde/EnterpriseInventoryAGODataSources"
# ArcGIS Server Table
arcGISServerInventoryTable = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde/EnterpriseInventoryArcGISServer"
# Domain Names Types and Values Table
domainTable = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde/EnterpriseInventoryDomainTable"
# Domain Usage Table
domainUsageTable = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde/EnterpriseInventoryDomainUsage"
# Database Content Table
databaseInventoryTable = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde/EnterpriseInventoryDatabaseContent"
# APRX REST Service Map Files Table
restAprxDatabaseTable = f"//{server_name}/d/PythonScripts/SDEFiles/AHS_PROD_EPHT.sde/EnterpriseInventoryRESTServiceMapFileData"
# SDE File Directory
databaseFileDirectory = f"//{server_name}/d/PythonScripts/SDEFiles"
# SDE File Names
databaseFileNames = ["ADAP_DEV_Admin.sde","ADAP_TEST_Admin.sde","ADAP_PROD_Admin.sde",
                     "AHS_DEV_EPHT.sde","AHS_TEST_EPHT.sde","AHS_PROD_EPHT.sde",
                     "EnvHealth_DEV_Admin.sde","EnvHealth_TEST_Admin.sde","EnvHealth_PROD_Admin.sde",
                     "HOC_DEV_Admin.sde","HOC_TEST_Admin.sde","HOC_PROD_Admin.sde",
                     "Surveillance_DEV_Admin.sde","Surveillance_TEST_Admin.sde","Surveillance_PROD_Admin.sde"]
# APRX Files Directory
RESTAprxDirectory = f"//{server_name}/d/RESTServices"
# Credentials files for ArcGIS Online and ArcGIS Server
serverCredsFile = f"//{server_name}/D/PythonScripts/creds/hashServerProd.txt"
agoCredsFile = f"//{server_name}/D/PythonScripts/creds/hashAGOIT.txt"

# Get server credentials
with open(serverCredsFile, 'r') as f:
    serverCreds = f.read().strip().split(',')
    agsUsername = serverCreds[0]
    agsPassword = serverCreds[1]
# Get AGO credentials
with open(agoCredsFile, 'r') as f:
    agoCreds = f.read().strip().split(',')
    agoUsername = agoCreds[0]
    agoPassword = agoCreds[1]

# ArcGIS Online URL and base URLs for ArcGIS Server
AGO_url = "https://ahs-vt.maps.arcgis.com/"
AGS_Base_URLs = ["https://maps.healthvermont.gov","https://mapstest.healthvermont.gov"]


# ArcGIS Online Function
def GetAGODataSources(AGO_url, agoInventoryTable, agoUsername, agoPassword):
    """
    Connects to ArcGIS Online, inventories all items, and interrogates each item
    for its underlying data sources. The results, including item details and the
    data source name and URL, are written to SQL.

    This function handles a wide variety of item types, including services, web maps,
    scenes, and various application types, to create a comprehensive catalog.
    """

    # Container for all data prior to SQL insertion    
    comprehensive_data_store = []

    gis = GIS(AGO_url, agoUsername, agoPassword)
    parent_url = gis.url
 
    # Get all users for the environment
    users = gis.users.search(max_users=2000)
    
    # Get user folder ids and names 
    user_folders = {}
    for user in users:
        userName = user.username
        folders = user.folders
        for folder in folders:
            folderProperties = folder.properties
            if 'name' in folderProperties:
                pass # This tests for root, which is handled later
            else:
                if userName not in user_folders:
                    user_folders[userName] = {}
                user_folders[userName][folderProperties['id']] = folderProperties['title']

    # --- Helper function for recursive parsing of data sources within maps and applications ---
    def _parse_layers_recursively(layer_list, parent_item_for_debug):
        """Recursively parse layer structures to find all data sources."""
        sources = []
        if not layer_list or not isinstance(layer_list, list):
            return sources
        
        for layer in layer_list:
            if not isinstance(layer, dict):
                print(f"  DEBUG: Item {parent_item_for_debug.id} has a malformed layer entry. Skipping.")
                continue

            layer_title = layer.get('title', '||UNTITLED LAYER||')
            layer_url = layer.get('url', None)
            
            if layer.get('layerType') == 'GroupLayer' and 'layers' in layer:
                sources.extend(_parse_layers_recursively(layer.get('layers', []), parent_item_for_debug))
            elif 'featureCollection' in layer:
                fc_layer_name = layer.get('title', '||UNTITLED FEATURE COLLECTION||')
                sources.append((fc_layer_name, "||EMBEDDED FEATURE COLLECTION||"))
            elif layer_url:
                sources.append((layer_title, layer_url))
        return sources

    # --- Main item processing loop ---
    all_items = gis.content.search(query="", max_items=10000)

    for item in all_items:
        try:
            item_id, item_type, item_name, item_url, item_owner = item.id, item.type, item.title, item.homepage, item.owner
            item_folder = user_folders.get(item_owner, {}).get(item.ownerFolder, 'root')
            found_sources = []
            
            # --- Logic for other service item types ---
            service_types = ('Feature Service', 'Map Service', 'Image Service', 'Vector Tile Service', 'Scene Service', 'KML', 'WMS', 'WMTS')
            if item_type in service_types and item.url:
                found_sources.append((item_name, item.url))

            elif item_type in ('Web Map', 'Web Scene'):
                data = item.get_data()
                if data and isinstance(data, str):
                    try: data = json.loads(data)
                    except json.JSONDecodeError: data = None 
                
                if data and isinstance(data, dict):
                    op_layers = data.get('operationalLayers', [])
                    found_sources.extend(_parse_layers_recursively(op_layers, item))
                    
                    if item_type == 'Web Map':
                        baseMap = data.get('baseMap', {})
                        if isinstance(baseMap, dict):
                            basemap_layers = baseMap.get('baseMapLayers', [])
                            found_sources.extend(_parse_layers_recursively(basemap_layers, item))
                        else:
                            print(f"  DEBUG: Item {item.id} ({item.title}) has a non-dictionary 'baseMap'.")

            elif item_type in ('Web Mapping Application', 'Dashboard', 'StoryMap', 'Web Experience', 'Hub Site Application'):
                data = item.get_data()
                if data and isinstance(data, str):
                    try: data = json.loads(data)
                    except json.JSONDecodeError: data = None

                if data and isinstance(data, dict):
                    map_ref = data.get('map')
                    if isinstance(map_ref, dict) and 'itemId' in map_ref:
                        map_id = map_ref['itemId']
                        found_sources.append((f"Referenced Web Map", f"{parent_url}/home/item.html?id={map_id}"))
                    
                    widgets = data.get('widgets', [])
                    if isinstance(widgets, list):
                        for widget in widgets:
                            if not isinstance(widget, dict):
                                print(f"  DEBUG: Item {item.id} ({item.title}) has a non-dictionary 'widget'.")
                                continue
                            
                            ds = widget.get('dataSource', {})
                            if isinstance(ds, dict) and 'itemId' in ds:
                                ds_item_id = ds['itemId']
                                ds_item = gis.content.get(ds_item_id)
                                ds_name = ds_item.title if ds_item else '||UNKNOWN ITEM||'
                                ds_url = ds_item.url if ds_item and ds_item.url else f"{parent_url}/home/item.html?id={ds_item_id}"
                                found_sources.append((f"Dashboard Source: {ds_name}", ds_url))
                    
                    dataSources = data.get('dataSources', {})
                    if isinstance(dataSources, dict):
                        for ds_id, ds_content in dataSources.items():
                            if not isinstance(ds_content, dict):
                                print(f"  DEBUG: Item {item.id} ({item.title}) has a non-dictionary 'dataSource' content for key '{ds_id}'.")
                                continue

                            if 'url' in ds_content:
                                ds_name = ds_content.get('label', ds_id)
                                found_sources.append((f"Experience Source: {ds_name}", ds_content['url']))
                            elif 'itemId' in ds_content:
                                ds_item_id = ds_content['itemId']
                                ds_url = f"{parent_url}/home/item.html?id={ds_item_id}"
                                found_sources.append((f"Experience Source Item", ds_url))

            # --- Add collected data for the item to the comprehensive store ---
            if not found_sources:
                row = (item_id, item_type, item_name, item_url, item_owner, item_folder, "N/A", "N/A")
                comprehensive_data_store.append(row)
            else:
                for layer_name, layer_url in found_sources:
                    row = (item_id, item_type, item_name, item_url, item_owner, item_folder, layer_name, layer_url if layer_url else "||NO URL FOUND||")
                    comprehensive_data_store.append(row)

        except Exception as e:
            error_message = f"Could not process item {item.id} ({item.title}): {str(e)}"
            print(f"ERROR: {error_message}")
            row = (item.id, item.type, item.title, item.homepage, item.owner, "ERROR", "PROCESSING ERROR", error_message[:255])
            comprehensive_data_store.append(row)

    try:
        # Clear the SQL table for updated data
        arcpy.management.TruncateTable(agoInventoryTable)
        
        # Insert all collected items
        fields = ["ItemID", "ItemType", "ItemName", "ItemURL", "AGOAccount", "AGOAccountFolder", "LayerName", "LayerURL"]
        with arcpy.da.InsertCursor(agoInventoryTable, fields) as insertCursor:
            for row_data in comprehensive_data_store:
                insertCursor.insertRow(row_data)

    except Exception as e:
        print(f"\nFATAL ERROR during database operation: {e}")
        print("Data was collected but the database could not be updated. The table may be empty or in an inconsistent state.")

# ArcGIS Server Function
def GetArcGISServerData(arcGISServerInventoryTable, AGS_Base_URLs, agsUsername, agsPassword):
    """ Connects to ArcGIS Server instances, retrieves service information,
    and writes service details to a SQL table.
    """

    # List to store service information
    services_info = []

    for AGS_Base_URL in AGS_Base_URLs:

        server = Server(url=f"{AGS_Base_URL}/arcgis/admin",
                            token_url=f"{AGS_Base_URL}/arcgis/tokens/generateToken",
                            username=agsUsername,
                            password=agsPassword,)
        
        # Get all directories in the server
        folders = server.services.folders

        # Iterate through each folder
        for folder in folders:
            # Get services in the folder
            services = server.services.list(folder=folder)  
            for service in services:

                serviceName = service.properties['serviceName']
                serviceType = service.properties['type']

                if folder == "/":
                    folderDirectory = "/"
                else:
                    folderDirectory = f"/{folder}/"

                # Get service details
                service_url = f"{AGS_Base_URL}/arcgis/rest/services{folderDirectory}{serviceName}/{serviceType}"
                
                # Request the service details
                response = requests.get(f"{service_url}?f=json")
                if response.status_code == 200:
                    service_data = response.json()

                    # Check if the service has layers
                    if 'layers' in service_data:

                        for layer in service_data['layers']:
                            layer_name = layer['name']
                            layer_id = layer['id']
                            
                            # Append the information to the list
                            services_info.append({
                                "serviceURL": service_url,
                                "serviceName": serviceName,
                                "serviceType": serviceType,
                                "layerName": layer_name,
                                "LayerID": layer_id,
                                "serviceLayerURL": f"{service_url}/{layer_id}"
                            })

    # Write to database table after clearing existing rows
    arcpy.management.TruncateTable(arcGISServerInventoryTable)
    fields = ["serviceURL","serviceName","serviceType","layerName","layerID","serviceLayerURL"]
    with arcpy.da.InsertCursor(arcGISServerInventoryTable, fields) as insertCursor:
        for service in services_info:
            serviceURL = service['serviceURL']
            serviceName = service['serviceName']
            serviceType = service['serviceType']
            layerName = service['layerName']
            layerID = service['LayerID']
            serviceLayerURL = service['serviceLayerURL']
            row = (serviceURL, serviceName, serviceType, layerName, layerID, serviceLayerURL)
            insertCursor.insertRow(row)

# Domain Data Function
def GetDomainData(domainTable, databaseFileDirectory, domainUsageTable, databaseFileNames):
    """
    Connects to each database in the specified directory, retrieves all domain
    and domain usage information, and writes it to two separate SQL tables.
    """

    # Store the collected data before writing to the database.
    domain_data_store = []
    domain_usage_data_store = []

    # Get Domain Information
    for database in databaseFileNames:
        try:
            sde_connection = os.path.join(databaseFileDirectory, database)
            domains = arcpy.da.ListDomains(sde_connection)
            # Get all domain names, types, and coded values/ranges
            for domain in domains:
                domainType = domain.domainType
                if domainType == 'CodedValue':
                    for code, description in domain.codedValues.items():
                        row = (domainType, database, domain.name, code, description)
                        domain_data_store.append(row)
                else: # Handles 'Range' domains
                    row = (domainType, database, domain.name, None, None)
                    domain_data_store.append(row)
        except Exception as e:
            print(f"    ERROR processing domains in {database}: {e}")

    # Collect Domain Usage Information
    for database in databaseFileNames:
        try:
            sde_connection = os.path.join(databaseFileDirectory, database)
            arcpy.env.workspace = sde_connection

            # Get all top-level tables and feature classes, plus those inside feature datasets
            datasets = arcpy.ListTables() + arcpy.ListFeatureClasses()
            feature_datasets = arcpy.ListDatasets(feature_type='Feature')
            for fds in feature_datasets:
                fds_datasets = arcpy.ListFeatureClasses(feature_dataset=fds) + arcpy.ListTables(fds)
                for fds_dataset in fds_datasets:
                    fds_dataset_basename = fds_dataset.split('.')[-1]
                    datasets.append(f"{fds}.{fds_dataset_basename}")
            for item in datasets: # This takes a while
                fields = arcpy.ListFields(item)
                for field in fields:
                    if field.domain:
                        row = (database, item, field.name, field.domain)
                        domain_usage_data_store.append(row)
        except Exception as e:
            print(f"    ERROR processing domain usage in {database}: {e}")

    # Clear tables and insert collected data
    try:

        # --- Populate the Domain Information Table ---
        arcpy.management.DeleteRows(domainTable)
        domainTableFields = ["DomainType", "DatabaseName", "DomainName", "Code", "Description"]
        with arcpy.da.InsertCursor(domainTable, domainTableFields) as cursor:
            for row_data in domain_data_store:
                cursor.insertRow(row_data)

        # --- Populate the Domain Usage Table ---
        print(f"  Truncating and populating table: {domainUsageTable}")
        arcpy.management.DeleteRows(domainUsageTable)
        domainUsageTableFields = ["DatabaseName", "TableName", "FieldName", "DomainName"]
        with arcpy.da.InsertCursor(domainUsageTable, domainUsageTableFields) as cursor:
            for row_data in domain_usage_data_store:
                cursor.insertRow(row_data)

    except Exception as e:
        print(f"\nFATAL ERROR during database operation: {e}")
        print("Data was collected, but the database could not be updated. Tables may be empty or inconsistent.")

# APRX File Data Function
def GetArcGISProRESTData(RESTAprxDirectory):

    # ArcGIS Pro Documents REST Directory ====================
    root_path = Path(RESTAprxDirectory)
    aprx_files = list(root_path.rglob('*.aprx'))
    arcpy.management.DeleteRows(restAprxDatabaseTable)
    aprxRESTfields = ["path_windows", "mapName", "layerName", "layerID", "ServerName", "DatabaseName", "DatasetName", "Datasource"]
    with arcpy.da.InsertCursor(restAprxDatabaseTable, aprxRESTfields) as insertCursor:
        for aprx_file in aprx_files:
            aprx_file_str = str(aprx_file).replace("\\", "/")

            aprx = arcpy.mp.ArcGISProject(aprx_file)

            for map in aprx.listMaps():
                mapName = map.name
                # Iterate through layers in the map
                for layer in map.listLayers():
                    layerName = layer.name
                    layerID = map.listLayers().index(layer)
                    layerSource = None
                    
                    if not layer.isGroupLayer:
                        if layer.supports("DATASOURCE"):
                            layerSource = layer.dataSource
                            
                            if "Server=" in layerSource:
                                # Extract the server name and database name from the data source
                                layerSourceData = layerSource.split(',')
                                serverName = layerSourceData[0].split('=')[1]
                                databaseName = layerSourceData[1].split('=')[1]
                                databaseUser = layerSourceData[3].split('=')[1]
                                datasetName = layerSourceData[-1].split('=')[1]
                                dataSource = f"{serverName}|{datasetName}"
                    
                    row = (aprx_file_str, mapName, layerName, layerID, serverName, databaseName, datasetName, dataSource)
                    insertCursor.insertRow(row)

# Database Content Function
def UpdateDatabaseContentTable(databaseInventoryTable):

    arcpy.management.DeleteRows(databaseInventoryTable)
    inventoryTableFieldList = ['databaseRoot', 'databaseCollectionName', 'datasetName', 'datasetType', 'geometryType', 'path', 'Datasource']
    # Loop through each database and add the data for each object in the database
    with arcpy.da.InsertCursor(databaseInventoryTable, inventoryTableFieldList) as insertCursor:
        for database in databaseFileNames:
            sde_connection = f"{databaseFileDirectory}/{database}"
            describeConnection = arcpy.Describe(sde_connection)
            serverName = describeConnection.connectionProperties.server

            for root, collections, tables in arcpy.da.Walk(sde_connection, datatype="Any", type="ALL"):
                if root == sde_connection:

                    # Root of database parameters
                    collectionName = None
                    datasetName = None
                    datasetType = "Enterprise Geodatabase"
                    geometryType = None
                    datasetPath = database
                    dataSource = f"{serverName}|{datasetName}"
                    row = [database, collectionName, datasetName, datasetType, geometryType, sde_connection, dataSource]
                    insertCursor.insertRow(row)

                    # Get root contents
                    for table in tables:
                        collectionName = None
                        datasetName = table
                        datasetPath = os.path.join(root, datasetName)
                        if arcpy.Exists(datasetPath):
                            datasetDescription = arcpy.Describe(datasetPath)
                            datasetType = datasetDescription.dataType
                            if str(datasetType.lower()) == "featureclass":
                                geometryType = datasetDescription.shapeType
                            else:
                                geometryType = None
                        else:
                            datasetType = "POTENTIALLY CORRUPTED DATASET"
                            geometryType = "POTENTIALLY CORRUPTED DATASET"
                        dataSource = f"{serverName}|{datasetName}"
                        row = [database, collectionName, datasetName, datasetType, geometryType, datasetPath, dataSource]
                        insertCursor.insertRow(row)

                else:
                    # Root of collection parameters
                    collectionName = os.path.basename(root)
                    datasetName = None
                    collectionDescription = arcpy.Describe(root)
                    collectionType = collectionDescription.dataType
                    geometryType = None
                    collectionPath = root
                    dataSource = f"{serverName}|{datasetName}"
                    row = [database, collectionName, datasetName, collectionType, geometryType, collectionPath, dataSource]
                    insertCursor.insertRow(row)
                
                    # Get collection contents
                    for table in tables:
                        collectionName = root
                        datasetName = table
                        datasetPath = os.path.join(root, datasetName)
                        if arcpy.Exists(datasetPath):
                            datasetDescription = arcpy.Describe(datasetPath)
                            datasetType = datasetDescription.dataType
                            if str(datasetType.lower()) == "featureclass":
                                geometryType = datasetDescription.shapeType
                            else:
                                geometryType = None
                        else:
                            datasetType = "POTENTIALLY CORRUPTED DATASET"
                            geometryType = "POTENTIALLY CORRUPTED DATASET"
                        dataSource = f"{serverName}|{datasetName}"
                        row = [database, collectionName, datasetName, datasetType, geometryType, datasetPath, dataSource]
                        insertCursor.insertRow(row)

# PowerBI Data is handled elsewhere, but included as a comment here as a reminder
#def UpdatePBIDataSources(PBIInventoryTable, PBIUsername, PBIPassword):
#    pass

# Main Function
def main():
    print("Updating AGO Data Sources...")
    GetAGODataSources(AGO_url, agoInventoryTable, agoUsername, agoPassword)

    print("Updating ArcGIS Server Data...")
    GetArcGISServerData(arcGISServerInventoryTable, AGS_Base_URLs, agsUsername, agsPassword)

    print("Updating Domain Data...")
    GetDomainData(domainTable,databaseFileDirectory,domainUsageTable)

    print("Updating ArcGIS Pro REST Data...")
    GetArcGISProRESTData(RESTAprxDirectory)

    print("Updating Database Content...")
    UpdateDatabaseContentTable(databaseInventoryTable)

# Main function
main()
