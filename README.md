# EnterpriseInventory

This project includes:

A Python file designed to query a series of environments to populate SQL tables with inventory data on Enterprise Geodatabases, APRX file map data sources, ArcGIS Server REST data, and ArcGIS Online Data items and data sources. The schema of the tables are designed to participate in relationships between entities (table -> map layer -> REST layer --> AGO data source) to enable the forensics of cross-environment tracing.

Web Application code in the form of HTML, JavaScript, and CSS files, to produce a web application that assists in this cross-environment tracing.

For the Web Application to function as intented, you must produce a REST service including all of your inventory tables, which is authenticated upon load.

Note that all code has been developed to mask servers, credentials, and identifiable information. If you use this code you should follow those same principles to protect sensitive information.

Please reach out to me for implementation questions

Daniel Jarvis (daniel.jarvis@vermont.gov)


# Deployment Instructions:

1) Download the EnterpriseInventorySchema.gdb.zip file from this repository and import all tables into your SQL Database of choice
2) Download the EnterpriseInventory.py file from this repository onto your Application server or ETL storage server
      Within the Python file, modify the the parameters located within the below subroutine bounding comments to match your organization:
         Organization Parameters start
         =======================
         =======================
         Organization Parameters end
      Set up an update cycle for this script to run that matches your organization's needs
3) Create an APRX file with an empy featureclass (a placeholder because ArcGIS Server requires a featureclass for a service to be published) and the inventory tables, then publish a REST service from this map
4) Download the index.html, app.js, and style.css files from this repository and store on your application server of choice. The following is an implementation that "piggybacks" on the the standalone ArcGIS Server web server
      On your application server that hosts standalone arcgisserver, place the html, js, and style files together in a single folder with a name of your choice. In this example I have placed them in a folder called EnterpriseInventory 
