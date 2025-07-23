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
      Set up an update cycle for this script to run that matches your organization's needs. I use FME Form and Flow. Reach out for assistance with this.
3) Create an APRX file with an empy featureclass (a placeholder because ArcGIS Server requires a featureclass for a service to be published) and the inventory tables, then publish a REST service from this map
4) Download the index.html, app.js, and style.css files from this repository and store on your application server of choice. The following is an implementation that "piggybacks" on the the standalone ArcGIS Server web server. On your application server that hosts standalone arcgisserver, place the html, js, and style files together in a single folder with a name of your choice within the webapps folder in the tomcat directory. If a webapps folder does not exist, create it first. In this example I have placed them in a folder called EnterpriseInventory:
<img width="935" height="181" alt="image" src="https://github.com/user-attachments/assets/dc660767-6624-493f-ad36-841a5464bbbc" />
5) Log into your reverse proxy server that ArcGIS Server is run through to expose the application externally, open IIS, and create a URL rewrite rule with the following parameters:
      Name: the name of your folder - in this case I am using EnterpriseInventory
      Pattern: the folder name and wildcards for finding the folder - in this case I wrote ^EnterpriseInventory/?(.*)
      Action Properties: this should include the external ip of your Application Server, and a port that is open both between your servers and to the external use where the application will be used, and will be in the form https://exeternalip:port/EnterpriseInventory/{R:1} 
<img width="1353" height="936" alt="image" src="https://github.com/user-attachments/assets/8f3e2387-3474-4514-8d08-8121a117a2e4" />

That should do it. Reach out to me for questions.


