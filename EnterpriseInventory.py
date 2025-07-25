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

# Organization Parameters start
# =======================

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
restAprxDirectory = f"//{server_name}/d/RESTServices"
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
ago_url = "https://ahs-vt.maps.arcgis.com/"
ags_Base_URLs = ["https://maps.healthvermont.gov","https://mapstest.healthvermont.gov"]

# =======================
# Organization Parameters end


# Utility functions

# ArcGIS Online Function
def GetAGODataSources(ago_url, agoInventoryTable, agoUsername, agoPassword):
    """
    Connects to ArcGIS Online, inventories all items, and interrogates each item
    for its underlying data sources. The results, including item details and the
    data source name and URL, are written to SQL.

    This function is compatible with multiple versions of the arcgis Python API by
    converting the user.folders property (which may be a list or a generator)
    to a list, and then inspecting its contents to determine the correct processing path.
    """

    # Container for all data prior to SQL insertion    
    comprehensive_data_store = []

    gis = GIS(ago_url, agoUsername, agoPassword)
    parent_url = gis.url
 
    # Get all users for the environment
    users = gis.users.search(max_users=2000)
    
    # Get user folder ids and names 
    user_folders = {}
    for user in users:
        userName = user.username

        # In newer versions, user.folders is a generator, which is not subscriptable.
        # Convert it to a list to safely handle both generators (new API) and lists (old API).
        folders_list = list(user.folders)
        
        if userName not in user_folders:
            user_folders[userName] = {}

        # Check if the user has any folders to process
        if folders_list:
            # Check the type of the first element to determine API behavior.
            if isinstance(folders_list[0], dict):
                # --- Path for OLDER arcgis versions (returns list of dictionaries) ---
                for folder in folders_list:
                    if 'id' in folder and 'title' in folder:
                        user_folders[userName][folder['id']] = folder['title']
            else:
                # --- Path for NEWER arcgis versions (returns list/generator of Folder objects) ---
                for folder in folders_list:
                    folderProperties = folder.properties
                    if 'id' in folderProperties and 'title' in folderProperties:
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
def GetArcGISServerData(arcGISServerInventoryTable, ags_Base_URLs, agsUsername, agsPassword):
    """
    Connects to ArcGIS Server instances, retrieves service information, and writes
    service details to a SQL table.

    This function is highly version-agnostic and compatible with modern (11.x) and
    very old (10.x) ArcGIS Enterprise environments. It handles three layers of
    potential API version differences:
    1. The services manager access point ('server.services' vs. 'server.manager').
    2. The structure of the returned folder list (list vs. generator).
    3. The method for accessing service properties (direct attribute vs. '.properties' dict).
    """
    services_info = []

    for ags_Base_URL in ags_Base_URLs:
        try:
            server = Server(url=f"{ags_Base_URL}/arcgis/admin",
                            token_url=f"{ags_Base_URL}/arcgis/tokens/generateToken",
                            username=agsUsername,
                            password=agsPassword)
            try:
                # --- Find the correct Service Manager ---
                if hasattr(server, 'services'):
                    # MODERN PATH (arcgis API >= 1.5)
                    service_manager = server.services
                elif hasattr(server, 'manager'):
                    # LEGACY PATH (arcgis API < 1.5)
                    service_manager = server.manager
                else:
                    print(f"ERROR: Could not find a valid services manager on server object for {ags_Base_URL}. Skipping.")
                    continue # Skip to the next server

                folders = list(service_manager.folders)
                if '/' not in folders:
                    folders.insert(0, '/')

                for folder in folders:
                    # For root folder, the folder parameter must be an empty string or not present
                    current_folder_path = folder if folder != '/' else ""
                    services = service_manager.list(folder=current_folder_path)
                    
                    for service in services:
                        try:
                            # Inner Try/Except for property access
                            try:
                                # Modern property access
                                serviceName = service.properties['serviceName']
                                serviceType = service.properties['type']
                            except (AttributeError, KeyError):
                                # Legacy property access
                                serviceName = service.serviceName
                                serviceType = service.type

                            status_dict = service.status
                            service_status = status_dict.get('realTimeState', 'UNKNOWN')
                            
                            folderDirectory = "/" if folder == "/" else f"/{folder}/"
                            service_url = f"{ags_Base_URL}/arcgis/rest/services{folderDirectory}{serviceName}/{serviceType}"

                            response = requests.get(f"{service_url}?f=json", verify=False) # Added verify=False for older servers with SSL issues
                            if response.status_code == 200:
                                service_data = response.json()
                                if 'layers' in service_data and service_data['layers']:
                                    for layer in service_data['layers']:
                                        services_info.append({
                                            "serviceURL": service_url,
                                            "serviceName": serviceName,
                                            "layerType": layer.get('type', 'Unknown Type'),
                                            "serviceType": serviceType,
                                            "layerName": layer.get('name', 'N/A'),
                                            "LayerID": layer.get('id', None),
                                            "serviceLayerURL": f"{service_url}/{layer.get('id', '')}",
                                            "serviceStatus": service_status
                                        })
                                else:
                                    services_info.append({
                                        "serviceURL": service_url,
                                        "serviceName": serviceName,
                                        "serviceType": serviceType,
                                        "layerName": 'N/A',
                                        "layerType": 'N/A',
                                        "LayerID": None,
                                        "serviceLayerURL": service_url,
                                        "serviceStatus": service_status
                                    })
                            else:
                                print(f"Warning: Could not access REST endpoint for {service_url}. Status: {response.status_code}")
                        except Exception as inner_e:
                            print(f"ERROR: Could not process service '{getattr(service, 'serviceName', 'UNKNOWN')}' in folder '{folder}'. Details: {inner_e}")

            except Exception as e:
                print(f"FATAL ERROR processing server {ags_Base_URL}: {e}")
                continue # Move to the next server in the list

        except Exception as conn_e:
            print(f"FATAL ERROR connecting to server {ags_Base_URL}: {conn_e}")
            
    # --- Update SQL Table ---
    try:
        arcpy.management.TruncateTable(arcGISServerInventoryTable)
        fields = ["serviceURL","serviceName","serviceType","layerName","layerType","layerID","serviceLayerURL","serviceStatus"]
        with arcpy.da.InsertCursor(arcGISServerInventoryTable, fields) as insertCursor:
            for service in services_info:
                row = (service["serviceURL"], 
                       service["serviceName"], 
                       service["serviceType"],
                       service["layerName"],
                       service["layerType"],
                       service["LayerID"],
                       service["serviceLayerURL"],
                       service["serviceStatus"]
                       )
                insertCursor.insertRow(row)
    except Exception as db_e:
        print(f"FATAL ERROR during database write operation: {db_e}")

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
def GetArcGISProRESTData(restAprxDirectory):

    # ArcGIS Pro Documents REST Directory ====================
    root_path = Path(restAprxDirectory)
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
def UpdateDatabaseContentTable(databaseInventoryTable, databaseFileNames, databaseFileDirectory):
    """
    Inventories the contents of enterprise geodatabases and populates a table with the findings.
    This script is designed to be compatible with multiple ArcGIS Pro versions.
    """
    try:
        # A list to hold dictionaries, where each dictionary represents a row.
        collected_data = []

        # --- Step 1: Data Collection ---
        # Loop through each database to collect information.
        for database in databaseFileNames:
            sde_connection = f"{databaseFileDirectory}/{database}"
            
            # Describe the connection to get properties.
            describeConnection = arcpy.Describe(sde_connection)
            connection_props = describeConnection.connectionProperties
            
            serverName = "Unknown"  # Default value
            # For newer versions of ArcGIS Pro (e.g., 3.3+)
            if hasattr(connection_props, 'server'):
                serverName = connection_props.server
            # For older versions (e.g., 3.2), fall back to the 'instance' property.
            elif hasattr(connection_props, 'instance'):
                instance_string = connection_props.instance
                serverName = instance_string.split('\\')[0]

            # Use arcpy.da.Walk to traverse the geodatabase.
            for root, collections, tables in arcpy.da.Walk(sde_connection, datatype="Any", type="ALL"):
                if root == sde_connection:
                    # This section processes the root of the geodatabase and items located there.
                    # Add a dictionary for the database connection itself.
                    collected_data.append({
                        'databaseRoot': database,
                        'databaseCollectionName': None,
                        'datasetName': None,
                        'datasetType': "Enterprise Geodatabase",
                        'geometryType': None,
                        'path': sde_connection,
                        'Datasource': f"{serverName}|"
                    })

                    # Process tables and feature classes at the root.
                    for table in tables:
                        datasetPath = os.path.join(root, table)
                        datasetDescription = arcpy.Describe(datasetPath) if arcpy.Exists(datasetPath) else None
                        
                        datasetType = datasetDescription.dataType if datasetDescription else "POTENTIALLY CORRUPTED DATASET"
                        geometryType = None
                        if datasetDescription and str(datasetType).lower() == "featureclass":
                            geometryType = datasetDescription.shapeType
                        
                        collected_data.append({
                            'databaseRoot': database,
                            'databaseCollectionName': None,
                            'datasetName': table,
                            'datasetType': datasetType,
                            'geometryType': geometryType,
                            'path': datasetPath,
                            'Datasource': f"{serverName}|{table}"
                        })

                else:
                    # This section processes collections (things like Feature Datasets) and their contents.
                    collectionName = os.path.basename(root)
                    collectionDescription = arcpy.Describe(root)
                    
                    # Add a dictionary for the collection.
                    collected_data.append({
                        'databaseRoot': database,
                        'databaseCollectionName': collectionName,
                        'datasetName': None,
                        'datasetType': collectionDescription.dataType,
                        'geometryType': None,
                        'path': root,
                        'Datasource': f"{serverName}|"
                    })
                
                    # Process contents of the collection.
                    for table in tables:
                        datasetPath = os.path.join(root, table)
                        datasetDescription = arcpy.Describe(datasetPath) if arcpy.Exists(datasetPath) else None
                        
                        datasetType = datasetDescription.dataType if datasetDescription else "POTENTIALLY CORRUPTED DATASET"
                        geometryType = None
                        if datasetDescription and str(datasetType).lower() == "featureclass":
                            geometryType = datasetDescription.shapeType
                            
                        collected_data.append({
                            'databaseRoot': database,
                            'databaseCollectionName': collectionName,
                            'datasetName': table,
                            'datasetType': datasetType,
                            'geometryType': geometryType,
                            'path': datasetPath,
                            'Datasource': f"{serverName}|{table}"
                        })

        # --- Step 2: Data Update ---
        # Now that all data is collected, update the database table.
        arcpy.management.DeleteRows(databaseInventoryTable)
        inventoryTableFieldList = ['databaseRoot', 'databaseCollectionName', 'datasetName', 'datasetType', 'geometryType', 'path', 'Datasource']        
        with arcpy.da.InsertCursor(databaseInventoryTable, inventoryTableFieldList) as insertCursor:
            for data_row in collected_data:
                # Create a list of values in the correct order for insertion.
                row_to_insert = [data_row[field] for field in inventoryTableFieldList]
                insertCursor.insertRow(row_to_insert)
                
    except arcpy.ExecuteError as e:
        print(f"An ArcPy error occurred: {e}")
    except Exception as e:
        print(f"A general error occurred: {e}")

# PowerBI Data is handled elsewhere, but included as a comment here as a reminder
#def UpdatePBIDataSources():
#    pass

# Main Function
def main():
    print("Updating AGO Data Sources...")
    GetAGODataSources(ago_url, agoInventoryTable, agoUsername, agoPassword)

    print("Updating ArcGIS Server Data...")
    GetArcGISServerData(arcGISServerInventoryTable, ags_Base_URLs, agsUsername, agsPassword)

    print("Updating Domain Data...")
    GetDomainData(domainTable, databaseFileDirectory, domainUsageTable, databaseFileNames)

    print("Updating ArcGIS Pro REST Data...")
    GetArcGISProRESTData(restAprxDirectory)

    print("Updating Database Content...")
    UpdateDatabaseContentTable(databaseInventoryTable, databaseFileNames, databaseFileDirectory)

# Main function
main()
