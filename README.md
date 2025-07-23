# EnterpriseInventory

This project includes:

A Python file designed to query a series of environments to populate SQL tables with inventory data on Enterprise Geodatabases, APRX file map data sources, ArcGIS Server REST data, and ArcGIS Online Data items and data sources. The schema of the tables are designed to participate in relationships between entities (table -> map layer -> REST layer --> AGO data source) to enable the forensics of cross-environment tracing.

Web Application code in the form of HTML, JavaScript, and CSS files, to produce a web application that assists in this cross-environment tracing.

For the Web Application to function as intented, you must produce a REST service including all of your inventory tables, which is authenticated upon load.

Note that all code has been developed to mask servers, credentials, and identifiable information. If you use this code you should follow those same principles to protect sensitive information.
