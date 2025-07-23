const CONFIG = {
    tokenUrl: "https://maps.healthvermont.gov/arcgis/tokens/generateToken",
    serverUrl: "https://maps.healthvermont.gov/arcgis/rest/services/EnterpriseInventory/MapServer",
    layers: {
        DATABASE_CONTENT: { id: 1, name: "Database Content" },
        APRX_REST_DATA:   { id: 2, name: "APRX REST Map Data" },
        AGS_DATA:         { id: 3, name: "ArcGIS Server Services" },
        AGO_DATA:         { id: 4, name: "AGO Data Sources" },
        DOMAIN_USAGE:     { id: 5, name: "Domain Usage" },
        DOMAIN_TABLE:     { id: 6, name: "Domain Table Definitions" },
        PBI_DATA:         { id: 7, name: "Power BI Data Sources" }
    },
    relationships: [
        { from: "DATABASE_CONTENT",   fromField: "Datasource",      to: "APRX_REST_DATA",     toField: "Datasource" },
        { from: "DATABASE_CONTENT",   fromField: "datasetName",     to: "DOMAIN_USAGE",       toField: "TableName" },
        { from: "DATABASE_CONTENT",   fromField: "databaseRoot",    to: "DOMAIN_USAGE",       toField: "DatabaseName" },
        { from: "DATABASE_CONTENT",   fromField: "databaseRoot",    to: "DOMAIN_TABLE",       toField: "DatabaseName" },
        { from: "APRX_REST_DATA",     fromField: "mapName",         to: "AGS_DATA",           toField: "serviceName" },
        { from: "AGS_DATA",           fromField: "serviceLayerURL", to: "AGO_DATA",           toField: "LayerURL" },
        { from: "AGS_DATA",           fromField: "serviceName",     to: "PBI_DATA",           toField: "RESTServiceName" },
        { from: "AGS_DATA",           fromField: "serviceURL",      to: "PBI_DATA",           toField: "RESTServiceURL" },
        { from: "AGS_DATA",           fromField: "serviceLayerURL", to: "PBI_DATA",           toField: "RESTServiceLayerURL" },
        { from: "AGO_DATA",           fromField: "LayerURL",        to: "AGO_DATA",           toField: "ItemURL" },
        { from: "DOMAIN_USAGE",       fromField: "DomainName",      to: "DOMAIN_TABLE",       toField: "DomainName" },
    ],
    searchableFields: {
        DATABASE_CONTENT: ['datasetName','Datasource'],
        APRX_REST_DATA:   ['DatasetName', 'mapName', 'path_windows'],
        AGS_DATA:         ['serviceURL'],
        AGO_DATA:         ['ItemName', 'LayerURL'],
        DOMAIN_USAGE:     ['DomainName'],
        DOMAIN_TABLE:     ['DomainName'],
        PBI_DATA:         ['Report', 'Workspace', 'RESTServiceURL', 'RESTServiceName', 'WebURL']
    }
};
const AppState = {
    token: null,
    allData: {},
    fieldAliases: {},
    layerFields: {},
    filteredData: [],
    currentTableId: null,
    currentResults: null,
    globalSearchResults: [],
    globallySelectedRecords: [],
    startTableIds: new Set(),
    initialTraceSelections: [], 
    discoveredRelationships: [], 
    networkInstance: null
};
let choicesInstances = { startTable: null, filters: {} };
let nodeModalInstance = null;
const DOMElements = {
    loginContainer: document.getElementById('login-container'),
    appContainer: document.getElementById('app-container'),
    loginError: document.getElementById('login-error'),
    loginButton: document.getElementById('login-button'),
    usernameInput: document.getElementById('username'),
    passwordInput: document.getElementById('password'),
    clearAllButton: document.getElementById('clear-all-button'),
    globalSearchInput: document.getElementById('global-search-input'),
    globalSearchButton: document.getElementById('global-search-button'),
    globalSearchResultsContainer: document.getElementById('global-search-results-container'),
    globalSearchSelectionInfo: document.getElementById('global-search-selection-info'),
    startTableSelect: document.getElementById('start-table-select'),
    filterControls: document.getElementById('filter-controls'),
    traceButton: document.getElementById('trace-button'),
    orphanReportButton: document.getElementById('orphan-report-button'),
    loopbackCheckbox: document.getElementById('loopback-checkbox'),
    bidirectionalCheckbox: document.getElementById('bidirectional-checkbox'),
    resultsContainer: document.getElementById('results-container'),
    mainLayout: document.getElementById('main-layout'),
    searchPane: document.getElementById('search-pane'),
    resizer: document.getElementById('resizer'),
    togglePaneBtn: document.getElementById('toggle-pane-btn'),
    viewSwitcher: document.getElementById('view-switcher'),
    viewTableBtn: document.getElementById('view-table-btn'),
    viewGraphBtn: document.getElementById('view-graph-btn'),
    graphContainer: document.getElementById('graph-container'),
    nodeDetailsModal: document.getElementById('node-details-modal'),
    nodeModalTitle: document.getElementById('node-modal-title'),
    nodeModalBody: document.getElementById('node-modal-body'),
    relationshipControlsContainer: document.getElementById('relationship-controls-container'),
    relationshipToggles: document.getElementById('relationship-toggles')
};
function sanitizeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str).replace(/</g, "<").replace(/>/g, ">");
}
async function handleLogin() {
    const username = DOMElements.usernameInput.value;
    const password = DOMElements.passwordInput.value;
    DOMElements.loginButton.disabled = true;
    DOMElements.loginButton.querySelector('.spinner-border').classList.remove('d-none');
    DOMElements.loginError.classList.add('d-none');
    try {
        const body = new URLSearchParams({ username, password, client: 'requestip', f: 'json' });
        const response = await fetch(CONFIG.tokenUrl, { method: 'POST', body });
        const data = await response.json();
        if (data.error) throw new Error(data.error.message || 'Authentication failed.');
        AppState.token = data.token;
        DOMElements.loginContainer.classList.add('d-none');
        DOMElements.appContainer.classList.remove('d-none');
        await prefetchAllData();
    } catch (error) {
        DOMElements.loginError.textContent = `Login Failed: ${error.message}`;
        DOMElements.loginError.classList.remove('d-none');
    } finally {
        DOMElements.loginButton.disabled = false;
        DOMElements.loginButton.querySelector('.spinner-border').classList.add('d-none');
    }
}
async function prefetchAllData() {
    DOMElements.resultsContainer.innerHTML = `<div class="d-flex align-items-center"><strong>Loading application data...</strong><div class="spinner-border ms-auto" role="status" aria-hidden="true"></div></div>`;
    try {
        const fetchPromises = Object.entries(CONFIG.layers).map(async ([key, layerConfig]) => {
            try {
                const metaUrl = `${CONFIG.serverUrl}/${layerConfig.id}?f=json&token=${AppState.token}`;
                const metaResponse = await fetch(metaUrl);
                if (!metaResponse.ok) throw new Error(`HTTP error ${metaResponse.status} for ${layerConfig.name} metadata`);
                const metaData = await metaResponse.json();
                if (metaData.error) throw new Error(`Metadata fetch failed for ${layerConfig.name}: ${metaData.error.message}`);
                AppState.layerFields[key] = metaData.fields;
                AppState.fieldAliases[key] = Object.fromEntries(metaData.fields.map(f => [f.name, f.alias]));
            } catch (error) {
                console.error(error);
                AppState.layerFields[key] = [];
                AppState.fieldAliases[key] = {};
                AppState.allData[key] = [];
                return;
            }
            try {
                const dataUrl = `${CONFIG.serverUrl}/${layerConfig.id}/query`;
                const params = new URLSearchParams({ where: '1=1', outFields: '*', returnGeometry: false, f: 'json', token: AppState.token });
                const dataResponse = await fetch(dataUrl, { method: 'POST', body: params });
                if (!dataResponse.ok) throw new Error(`HTTP error ${dataResponse.status} for ${layerConfig.name} data`);
                const data = await dataResponse.json();
                if (data.error) throw new Error(`Data fetch failed for ${layerConfig.name}: ${data.error.message}`);
                AppState.allData[key] = data.features.map(f => f.attributes);
            } catch (error) {
                console.error(error);
                AppState.allData[key] = [];
            }
        });
        await Promise.all(fetchPromises);
        DOMElements.resultsContainer.innerHTML = `<div class="alert alert-info">Use the controls on the left to find a record and trace its relationships.</div>`;
        populateTableSelect();
        DOMElements.orphanReportButton.disabled = false;
    } catch (error) {
        console.error("Critical error during application initialization:", error);
        DOMElements.resultsContainer.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> Failed to initialize application data. Please check the console for details or try logging in again.</div>`;
    }
}
function togglePane() {
    const isCollapsed = DOMElements.mainLayout.classList.toggle('pane-collapsed');
    DOMElements.togglePaneBtn.innerHTML = isCollapsed ? '»' : '«';
    const newTitle = isCollapsed ? 'Expand Pane' : 'Collapse Pane';
    DOMElements.togglePaneBtn.title = newTitle;
    DOMElements.togglePaneBtn.setAttribute('aria-label', newTitle);
}
function initPaneControls() {
    const pane = DOMElements.searchPane;
    const layout = DOMElements.mainLayout;
    let originalWidth = pane.offsetWidth;
    const minWidth = 320; 
    const handleResize = (e) => {
        e.preventDefault();
        const containerOffsetLeft = layout.getBoundingClientRect().left;
        let newWidth = e.clientX - containerOffsetLeft;
        const maxAllowedWidth = layout.offsetWidth - 100;
        if (newWidth < minWidth) newWidth = minWidth;
        if (newWidth > maxAllowedWidth) newWidth = maxAllowedWidth;
        layout.style.setProperty('--search-pane-width', `${newWidth}px`);
    };
    const stopResize = () => {
        document.body.classList.remove('is-resizing');
        window.removeEventListener('mousemove', handleResize);
        window.removeEventListener('mouseup', stopResize);
    };
    DOMElements.resizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        originalWidth = pane.offsetWidth;
        document.body.classList.add('is-resizing');
        window.addEventListener('mousemove', handleResize);
        window.addEventListener('mouseup', stopResize);
    });
    DOMElements.resizer.addEventListener('dblclick', () => {
        const currentWidthPx = pane.offsetWidth;
        const wideStateWidth = window.innerWidth * 0.6;
        if (currentWidthPx > wideStateWidth) {
            layout.style.setProperty('--search-pane-width', originalWidth > minWidth ? `${originalWidth}px` : '50%');
        } else {
            layout.style.setProperty('--search-pane-width', '60%');
        }
    });
}
function handleClearAll() {
    resetGlobalSearch();
    resetFilterSelection();
    resetRelationshipToggles();
    DOMElements.resultsContainer.innerHTML = `<div class="alert alert-info">Use the controls on the left to find a record and trace its relationships.</div>`;
    DOMElements.graphContainer.innerHTML = '';
    DOMElements.graphContainer.classList.add('d-none');
    DOMElements.viewSwitcher.classList.add('d-none');
    DOMElements.resultsContainer.classList.remove('d-none');
    AppState.currentResults = null;
    AppState.startTableIds.clear();
    AppState.initialTraceSelections = [];
    updateTraceButtonState();
}
function handleGlobalSearch() {
    const rawSearchTerm = DOMElements.globalSearchInput.value.trim().toLowerCase();
    const keywords = rawSearchTerm.split(' ').filter(k => k);
    if (keywords.length === 0) {
        AppState.globalSearchResults = [];
        renderGlobalSearchResults();
        return;
    }
    resetFilterSelection();
    const spinner = DOMElements.globalSearchButton.querySelector('.spinner-border');
    spinner.classList.remove('d-none');
    DOMElements.globalSearchButton.disabled = true;
    setTimeout(() => {
        const found = [];
        for (const [tableId, allowedFields] of Object.entries(CONFIG.searchableFields)) {
            const records = AppState.allData[tableId];
            if (!records) continue;
            for (const record of records) {
                for (const fieldName of allowedFields) {
                    const value = record[fieldName];
                    if (value) {
                        const valueLower = String(value).toLowerCase();
                        if (keywords.every(keyword => valueLower.includes(keyword))) {
                            found.push({ record, tableId, matchingField: fieldName, matchingValue: value });
                            break; 
                        }
                    }
                }
            }
        }
        AppState.globalSearchResults = found;
        renderGlobalSearchResults();
        spinner.classList.add('d-none');
        DOMElements.globalSearchButton.disabled = false;
    }, 10);
}
function renderGlobalSearchResults() {
    const container = DOMElements.globalSearchResultsContainer;
    container.innerHTML = '';
    const uniqueRecords = new Map();
    AppState.globalSearchResults.forEach((result, index) => {
        const uniqueKey = `${result.tableId}-${result.record.OBJECTID}`;
        if (!uniqueRecords.has(uniqueKey)) {
            uniqueRecords.set(uniqueKey, { ...result, originalIndex: index });
        }
    });
    if (uniqueRecords.size === 0) {
        if (DOMElements.globalSearchInput.value.trim()) {
            container.innerHTML = `<div class="text-muted p-2 small">No results found.</div>`;
        }
        return;
    }
    const selectAllContainer = document.createElement('div');
    selectAllContainer.className = 'form-check form-switch p-2 border-bottom bg-light';
    selectAllContainer.innerHTML = `
        <input class="form-check-input" type="checkbox" role="switch" id="global-search-select-all">
        <label class="form-check-label small fw-bold" for="global-search-select-all"> Select / Deselect All (${uniqueRecords.size} unique items) </label>
    `;
    container.appendChild(selectAllContainer);
    const list = document.createElement('ul');
    list.className = 'list-group list-flush';
    uniqueRecords.forEach((result) => {
        const { record, tableId, matchingField, originalIndex } = result;
        const layerName = CONFIG.layers[tableId].name;
        const fieldAlias = AppState.fieldAliases[tableId]?.[matchingField] || matchingField;
        const displayValue = sanitizeHTML(record[matchingField]);
        const li = document.createElement('li');
        li.className = 'list-group-item search-result-item p-0';
        li.innerHTML = `
            <div class="input-group input-group-sm">
                <div class="input-group-text">
                    <input class="form-check-input mt-0" type="checkbox" data-result-index="${originalIndex}" aria-label="Select this record">
                </div>
                <div class="form-control form-control-sm border-0" style="height: auto;">
                    <div class="fw-bold">${sanitizeHTML(layerName)}</div>
                    <small class="text-muted">Match on <i>${sanitizeHTML(fieldAlias)}</i>: "${displayValue}"</small>
                </div>
            </div>
        `;
        list.appendChild(li);
    });
    container.appendChild(list);
}
function handleGlobalResultSelection(checkbox) {
    resetFilterSelection();
    const resultIndex = parseInt(checkbox.dataset.resultIndex, 10);
    const selectedResult = AppState.globalSearchResults[resultIndex];
    const uniqueId = `${selectedResult.tableId}-${selectedResult.record.OBJECTID}`;
    if (checkbox.checked) {
        if (!AppState.globallySelectedRecords.some(r => r.uniqueId === uniqueId)) {
            AppState.globallySelectedRecords.push({ ...selectedResult, uniqueId });
        }
    } else {
        AppState.globallySelectedRecords = AppState.globallySelectedRecords.filter(r => r.uniqueId !== uniqueId);
    }
    updateGlobalSelectionUI();
}
function handleGlobalSelectAll(checkbox) {
    const isChecked = checkbox.checked;
    resetFilterSelection();
    AppState.globallySelectedRecords = [];
    if (isChecked) {
        const uniqueRecords = new Map();
        AppState.globalSearchResults.forEach(result => {
            const uniqueId = `${result.tableId}-${result.record.OBJECTID}`;
            if (!uniqueRecords.has(uniqueId)) {
                uniqueRecords.set(uniqueId, { ...result, uniqueId });
            }
        });
        AppState.globallySelectedRecords = Array.from(uniqueRecords.values());
    }
    const allCheckboxes = DOMElements.globalSearchResultsContainer.querySelectorAll('.search-result-item .form-check-input');
    allCheckboxes.forEach(cb => cb.checked = isChecked);
    updateGlobalSelectionUI();
}
function updateGlobalSelectionUI() {
    const count = AppState.globallySelectedRecords.length;
    if (count > 0) {
        DOMElements.globalSearchSelectionInfo.innerHTML = `<strong>${count}</strong> record(s) selected.`;
        DOMElements.globalSearchSelectionInfo.classList.remove('d-none');
    } else {
        DOMElements.globalSearchSelectionInfo.classList.add('d-none');
    }
    const selectAllCheckbox = document.getElementById('global-search-select-all');
    if (selectAllCheckbox) {
        const uniqueItemsInResults = new Set(AppState.globalSearchResults.map(r => `${r.tableId}-${r.record.OBJECTID}`)).size;
        selectAllCheckbox.checked = (count > 0 && count === uniqueItemsInResults);
        selectAllCheckbox.indeterminate = (count > 0 && count < uniqueItemsInResults);
    }
    updateTraceButtonState();
}
function delegateGlobalSearchEvents(e) {
    const target = e.target;
    if (target.id === 'global-search-select-all') {
        handleGlobalSelectAll(target);
    } else if (target.closest('.search-result-item .form-check-input')) {
        handleGlobalResultSelection(target);
    }
}
function resetGlobalSearch() {
    DOMElements.globalSearchInput.value = '';
    DOMElements.globalSearchResultsContainer.innerHTML = '';
    DOMElements.globalSearchSelectionInfo.classList.add('d-none');
    AppState.globalSearchResults = [];
    AppState.globallySelectedRecords = [];
    updateTraceButtonState();
}
function resetFilterSelection() {
    if (choicesInstances.startTable && choicesInstances.startTable.getValue(true)) {
        choicesInstances.startTable.setChoiceByValue('');
    }
    DOMElements.filterControls.innerHTML = '';
    Object.values(choicesInstances.filters).forEach(instance => instance.destroy());
    choicesInstances.filters = {};
    AppState.filteredData = [];
    AppState.currentTableId = null;
    updateTraceButtonState();
}
function populateTableSelect() {
    if (choicesInstances.startTable) choicesInstances.startTable.destroy();
    const options = Object.entries(CONFIG.layers).map(([key, layer]) => ({
        value: key,
        label: `${layer.name} (${AppState.allData[key]?.length || 0} records)`
    }));
    options.unshift({ value: '', label: 'Choose a table...', placeholder: true });
    choicesInstances.startTable = new Choices(DOMElements.startTableSelect, {
        searchEnabled: true,
        itemSelectText: '',
        shouldSort: false
    });
    choicesInstances.startTable.setChoices(options, 'value', 'label', true);
}
function handleTableSelectChange(event) {
    resetGlobalSearch();
    AppState.currentTableId = event.detail.value;
    if (!AppState.currentTableId) {
        DOMElements.filterControls.innerHTML = '';
        return;
    }
    DOMElements.viewSwitcher.classList.add('d-none');
    updateFilterUI();
}
function updateFilterUI() {
    DOMElements.filterControls.innerHTML = '';
    Object.values(choicesInstances.filters).forEach(instance => instance.destroy());
    choicesInstances.filters = {};
    const selectedData = AppState.allData[AppState.currentTableId];
    if (!selectedData || selectedData.length === 0) {
        DOMElements.filterControls.innerHTML = `<div class="alert alert-warning small p-2 mt-2" role="alert">This layer has no data to filter.</div>`;
        AppState.filteredData = [];
        updateTraceButtonState();
        return;
    }
    AppState.filteredData = [...selectedData];
    addFilterControl(1);
    updateTraceButtonState();
}
function addFilterControl(level) {
    if (!AppState.currentTableId || AppState.filteredData.length === 0) return;
    const filterDiv = document.createElement('div');
    filterDiv.className = 'filter-group mb-3';
    filterDiv.id = `filter-group-${level}`;
    filterDiv.innerHTML = `
        <label for="filter-field-${level}" class="form-label small">Filter ${level} by field:</label>
        <select id="filter-field-${level}"></select>
        <label for="filter-value-${level}" class="form-label small mt-2">Value:</label>
        <select id="filter-value-${level}"></select>
    `;
    DOMElements.filterControls.appendChild(filterDiv);
    const fieldSelect = document.getElementById(`filter-field-${level}`);
    const valueSelect = document.getElementById(`filter-value-${level}`);
    const currentDataForOptions = AppState.filteredData;
    const allFieldsFromDefinition = AppState.layerFields[AppState.currentTableId] || [];
    const excludedFields = ['objectid', 'shape', 'shape_length', 'shape_area', 'globalid'];
    const filteredFields = allFieldsFromDefinition
        .filter(field => !excludedFields.includes(field.name.toLowerCase()))
        .sort((a, b) => (a.alias || a.name).localeCompare(b.alias || b.name));
    const fieldOptions = [
        { value: '', label: 'Select field...', placeholder: true },
        ...filteredFields.map(field => ({ value: field.name, label: field.alias || field.name }))
    ];
    const fieldChoices = new Choices(fieldSelect, { searchEnabled: true, itemSelectText: '', shouldSort: false });
    fieldChoices.setChoices(fieldOptions, 'value', 'label', true);
    choicesInstances.filters[`field-${level}`] = fieldChoices;
    const valueChoices = new Choices(valueSelect, {
        searchEnabled: true,
        itemSelectText: '',
        placeholder: true,
        shouldSort: false,
    });
    valueChoices.disable();
    choicesInstances.filters[`value-${level}`] = valueChoices;
    fieldSelect.addEventListener('change', (event) => {
        const selectedField = event.detail.value;
        if (!selectedField) return;
        const uniqueValues = [...new Set(currentDataForOptions.map(row => row[selectedField]).filter(v => v != null && v !== ''))].sort();
        const valueOptions = [{ value: '', label: 'Select value...', placeholder: true }, ...uniqueValues.map(val => ({ value: val, label: String(val) }))];
        valueChoices.clearStore();
        valueChoices.setChoices(valueOptions, 'value', 'label', true);
        valueChoices.enable();
    });
    valueSelect.addEventListener('change', (event) => {
        const selectedValue = event.detail.value;
        if (!selectedValue) return;
        const selectedField = fieldChoices.getValue(true);
        AppState.filteredData = AppState.filteredData.filter(row => String(row[selectedField]) === String(selectedValue));
        let nextLevel = level + 1;
        while (document.getElementById(`filter-group-${nextLevel}`)) {
            choicesInstances.filters[`field-${nextLevel}`]?.destroy();
            choicesInstances.filters[`value-${nextLevel}`]?.destroy();
            delete choicesInstances.filters[`field-${nextLevel}`];
            delete choicesInstances.filters[`value-${nextLevel}`];
            document.getElementById(`filter-group-${nextLevel}`).remove();
            nextLevel++;
        }
        addFilterControl(level + 1);
        updateTraceButtonState();
    });
}
function updateTraceButtonState() {
    const totalRecordsInTable = AppState.allData[AppState.currentTableId]?.length || 0;
    const filterSelectionMade = AppState.filteredData.length > 0 && (AppState.filteredData.length < totalRecordsInTable || totalRecordsInTable === 1);
    const globalSearchSelectionMade = AppState.globallySelectedRecords.length > 0;
    const hasSelection = filterSelectionMade || globalSearchSelectionMade;
    const count = filterSelectionMade ? AppState.filteredData.length : AppState.globallySelectedRecords.length;
    DOMElements.traceButton.disabled = !hasSelection;
    DOMElements.traceButton.textContent = hasSelection ? `Show Relationships (${count} selected)` : 'Show Relationships';
}
function startRelationshipTrace() {
    AppState.startTableIds.clear();
    AppState.initialTraceSelections = [];
    if (AppState.globallySelectedRecords.length > 0) {
        AppState.initialTraceSelections = AppState.globallySelectedRecords;
    } else if (AppState.filteredData.length > 0 && AppState.currentTableId) {
        AppState.initialTraceSelections = AppState.filteredData.map(record => ({ record, tableId: AppState.currentTableId }));
    } else {
        alert("No records selected to trace.");
        return;
    }
    AppState.initialTraceSelections.forEach(sel => AppState.startTableIds.add(sel.tableId));
    const fullTraceResults = performTrace(AppState.initialTraceSelections, CONFIG.relationships);
    const usedRelationshipIndices = new Set();
    CONFIG.relationships.forEach((rel, index) => {
        if (fullTraceResults.hasOwnProperty(rel.from) && fullTraceResults.hasOwnProperty(rel.to)) {
             const fromRecords = fullTraceResults[rel.from];
             const toRecords = fullTraceResults[rel.to];
             const hasLink = fromRecords.some(fromR => 
                toRecords.some(toR => 
                    fromR[rel.fromField] != null && 
                    String(fromR[rel.fromField]).toLowerCase() === String(toR[rel.toField]).toLowerCase()
                )
             );
             if (hasLink) {
                usedRelationshipIndices.add(index);
             }
        }
    });
    AppState.discoveredRelationships = Array.from(usedRelationshipIndices).map(index => ({
        index,
        ...CONFIG.relationships[index]
    }));
    AppState.currentResults = fullTraceResults;
    renderResults(fullTraceResults);
    renderRelationshipToggles();
    DOMElements.viewSwitcher.classList.remove('d-none');
    switchView('table');
    if (!DOMElements.mainLayout.classList.contains('pane-collapsed')) {
        togglePane();
    }
}
function performTrace(initialSelections, activeRelationships) {
    const allowLoopback = DOMElements.loopbackCheckbox.checked;
    const isBiDirectional = DOMElements.bidirectionalCheckbox.checked;
    const foundRecordsByTable = {};
    const queue = [];
    const processedLinks = new Set();
    initialSelections.forEach(selection => {
        const { record, tableId } = selection;
        if (!foundRecordsByTable[tableId]) {
            foundRecordsByTable[tableId] = [];
        }
        const isDuplicate = foundRecordsByTable[tableId].some(existing => existing.OBJECTID === record.OBJECTID);
        if (!isDuplicate) {
            foundRecordsByTable[tableId].push(record);
            queue.push({ tableId, records: [record] });
        }
    });
    while (queue.length > 0) {
        const { tableId: currentTableId, records } = queue.shift();
        activeRelationships.forEach(rel => {
            let sourceTable, sourceField, targetTable, targetField;
            let shouldTrace = false;
            if (rel.from === currentTableId) {
                [sourceTable, sourceField, targetTable, targetField] = [rel.from, rel.fromField, rel.to, rel.toField];
                shouldTrace = true;
            } 
            else if (isBiDirectional && rel.to === currentTableId) {
                [sourceTable, sourceField, targetTable, targetField] = [rel.to, rel.toField, rel.from, rel.fromField];
                shouldTrace = true;
            }
            if (shouldTrace) {
                if (!allowLoopback && AppState.startTableIds.has(targetTable)) return;
                const linkValues = [...new Set(records.map(r => r[sourceField]).filter(v => v != null))];
                linkValues.forEach(val => {
                    const linkKey = `${sourceTable}:${sourceField}:${val}->${targetTable}:${targetField}`;
                    if (processedLinks.has(linkKey)) return;
                    processedLinks.add(linkKey);
                    const targetData = AppState.allData[targetTable] || [];
                    const matches = targetData.filter(row => String(row[targetField]).toLowerCase() === String(val).toLowerCase());
                    if (matches.length > 0) {
                        if (!foundRecordsByTable[targetTable]) foundRecordsByTable[targetTable] = [];
                        matches.forEach(match => {
                            const isDuplicate = foundRecordsByTable[targetTable].some(existing => existing.OBJECTID === match.OBJECTID);
                            if (!isDuplicate) {
                                foundRecordsByTable[targetTable].push(match);
                                queue.push({ tableId: targetTable, records: [match] });
                            }
                        });
                    }
                });
            }
        });
    }
    return foundRecordsByTable;
}
function renderRelationshipToggles() {
    const container = DOMElements.relationshipToggles;
    container.innerHTML = '';
    if (AppState.discoveredRelationships.length === 0) {
        DOMElements.relationshipControlsContainer.classList.add('d-none');
        return;
    }
    AppState.discoveredRelationships.forEach(rel => {
        const fromLayerName = CONFIG.layers[rel.from].name;
        const toLayerName = CONFIG.layers[rel.to].name;
        const label = document.createElement('label');
        label.className = 'list-group-item';
        label.innerHTML = `
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" role="switch" value="${rel.index}" checked>
                <div class="ms-2">
                    <small class="d-block"><strong>${sanitizeHTML(fromLayerName)}</strong></small>
                    <small class="d-block text-muted">⮂ via <i>${sanitizeHTML(rel.fromField)} / ${sanitizeHTML(rel.toField)}</i></small>
                    <small class="d-block"><strong>${sanitizeHTML(toLayerName)}</strong></small>
                </div>
            </div>
        `;
        container.appendChild(label);
    });
    DOMElements.relationshipControlsContainer.classList.remove('d-none');
}
function handleRelationshipToggle() {
    const checkedToggles = DOMElements.relationshipToggles.querySelectorAll('input:checked');
    const activeRelationshipIndices = Array.from(checkedToggles).map(input => parseInt(input.value, 10));
    const activeRelationships = CONFIG.relationships.filter((_, index) => activeRelationshipIndices.includes(index));
    const newResults = performTrace(AppState.initialTraceSelections, activeRelationships);
    AppState.currentResults = newResults;
    renderResults(newResults);
    if (!DOMElements.graphContainer.classList.contains('d-none')) {
        renderGraphView(newResults);
    }
}
function resetRelationshipToggles() {
    DOMElements.relationshipControlsContainer.classList.add('d-none');
    DOMElements.relationshipToggles.innerHTML = '';
    AppState.discoveredRelationships = [];
    if (AppState.networkInstance) {
        AppState.networkInstance.destroy();
        AppState.networkInstance = null;
    }
}
async function generateOrphanReport() {
    const button = DOMElements.orphanReportButton;
    const spinner = button.querySelector('.spinner-border');
    const buttonText = button.querySelector('span:not(.spinner-border)');
    button.disabled = true;
    spinner.classList.remove('d-none');
    buttonText.textContent = ' Generating...';
    DOMElements.resultsContainer.innerHTML = `<div class="d-flex align-items-center"><strong>Analyzing all tables for orphan records...</strong><div class="spinner-border ms-auto" role="status" aria-hidden="true"></div></div>`;
    DOMElements.graphContainer.classList.add('d-none');
    DOMElements.resultsContainer.classList.remove('d-none');
    DOMElements.viewSwitcher.classList.add('d-none');
    await new Promise(resolve => setTimeout(resolve, 50));
    try {
        const orphanResults = findOrphanRecords();
        renderOrphanReport(orphanResults);
        if (!DOMElements.mainLayout.classList.contains('pane-collapsed')) {
            togglePane();
        }
    } catch (error) {
        console.error("Error generating orphan report:", error);
        DOMElements.resultsContainer.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> Could not generate the orphan report. See console for details.</div>`;
    } finally {
        button.disabled = false;
        spinner.classList.add('d-none');
        buttonText.textContent = ' Generate Orphan Report';
    }
}
function findOrphanRecords() {
    const connectionEndpoints = new Map();
    for (const rel of CONFIG.relationships) {
        const processSide = (tableId, fieldName) => {
            const mapKey = `${tableId}:${fieldName}`;
            if (!connectionEndpoints.has(mapKey)) {
                const values = new Set(
                    (AppState.allData[tableId] || [])
                    .map(record => record[fieldName])
                    .filter(v => v != null && String(v).trim() !== '')
                    .map(v => String(v).toLowerCase())
                );
                connectionEndpoints.set(mapKey, values);
            }
        };
        processSide(rel.from, rel.fromField);
        processSide(rel.to, rel.toField);
    }
    const orphanResults = {};
    for (const tableId of Object.keys(AppState.allData)) {
        const records = AppState.allData[tableId];
        if (!records || records.length === 0) continue;
        const orphansInThisTable = records.filter(record => {
            let isConnected = false;
            for (const rel of CONFIG.relationships) {
                let sourceField, targetTable, targetField;
                if (rel.from === tableId) {
                    [sourceField, targetTable, targetField] = [rel.fromField, rel.to, rel.toField];
                } else if (rel.to === tableId) {
                    [sourceField, targetTable, targetField] = [rel.toField, rel.from, rel.fromField];
                } else {
                    continue;
                }
                const sourceValue = record[sourceField];
                if (sourceValue == null || String(sourceValue).trim() === '') {
                    continue;
                }
                const targetMapKey = `${targetTable}:${targetField}`;
                const targetValues = connectionEndpoints.get(targetMapKey);
                if (targetValues && targetValues.has(String(sourceValue).toLowerCase())) {
                    isConnected = true;
                    break;
                }
            }
            return !isConnected;
        });
        if (orphansInThisTable.length > 0) {
            orphanResults[tableId] = orphansInThisTable;
        }
    }
    return orphanResults;
}
function renderOrphanReport(orphanResults) {
    const container = DOMElements.resultsContainer;
    container.innerHTML = '';
    const totalOrphans = Object.values(orphanResults).reduce((sum, records) => sum + records.length, 0);
    const tablesWithOrphansCount = Object.keys(orphanResults).length;
    const heading = document.createElement('div');
    heading.className = 'mb-3';
    if (totalOrphans > 0) {
        heading.innerHTML = `<h2>Orphan Records Report</h2><p class="text-muted">Found a total of <strong>${totalOrphans}</strong> orphan record(s) across <strong>${tablesWithOrphansCount}</strong> table(s).</p>`;
    } else {
        heading.innerHTML = `<h2>Orphan Records Report</h2><div class="alert alert-success mt-3" role="alert"><h4 class="alert-heading">Excellent!</h4><p>No orphan records were found.</p></div>`;
    }
    container.appendChild(heading);
    if (totalOrphans === 0) return;
    const sortedTableIds = Object.keys(orphanResults).sort((a, b) =>
        Object.keys(CONFIG.layers).indexOf(a) - Object.keys(CONFIG.layers).indexOf(b)
    );
    sortedTableIds.forEach(tableId => {
        const records = orphanResults[tableId];
        const layerName = CONFIG.layers[tableId].name;
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.innerHTML = `<span>${sanitizeHTML(layerName)}</span><span class="badge bg-warning text-dark">${records.length} orphan records</span>`;
        details.appendChild(summary);
        details.appendChild(createInteractiveTableContainer(records, tableId));
        container.appendChild(details);
    });
}
function switchView(viewName) {
    const isTableView = viewName === 'table';
    DOMElements.viewTableBtn.classList.toggle('active', isTableView);
    DOMElements.viewGraphBtn.classList.toggle('active', !isTableView);
    DOMElements.resultsContainer.classList.toggle('d-none', !isTableView);
    DOMElements.graphContainer.classList.toggle('d-none', isTableView);
    if (!isTableView) {
        renderGraphView(AppState.currentResults);
    }
}
function renderResults(results) {
    const container = DOMElements.resultsContainer;
    container.innerHTML = '';
    const sortedTableIds = Object.keys(results).sort((a, b) =>
        Object.keys(CONFIG.layers).indexOf(a) - Object.keys(CONFIG.layers).indexOf(b)
    );
    sortedTableIds.forEach(tableId => {
        const records = results[tableId];
        const layerName = CONFIG.layers[tableId].name;
        const isInitial = AppState.startTableIds.has(tableId);
        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.className = isInitial ? 'text-primary' : '';
        summary.innerHTML = `<span>${sanitizeHTML(layerName)}</span><span class="badge bg-${isInitial ? 'primary' : 'secondary'}">${records.length} records</span>`;
        details.appendChild(summary);
        details.appendChild(createInteractiveTableContainer(records, tableId));
        container.appendChild(details);
    });
}
function createInteractiveTableContainer(records, tableId) {
    const wrapper = document.createElement('div');
    wrapper.className = 'interactive-table-wrapper';
    if (!records || records.length === 0) {
        wrapper.innerHTML = '<p class="text-muted p-3">No related records found.</p>';
        return wrapper;
    }
    const searchInput = document.createElement('input');
    searchInput.type = 'search';
    searchInput.placeholder = `Search ${records.length} records...`;
    searchInput.className = 'form-control form-control-sm mb-2 table-search-input';
    searchInput.setAttribute('data-target-table', `table-${tableId}`);
    const tableContainer = document.createElement('div');
    tableContainer.className = 'table-responsive';
    tableContainer.innerHTML = createHtmlTable(records, tableId);
    wrapper.appendChild(searchInput);
    wrapper.appendChild(tableContainer);
    const table = tableContainer.querySelector('table');
    if(table) table.id = `table-${tableId}`;
    return wrapper;
}
function createHtmlTable(records, tableId) {
    if (!records || records.length === 0) return '';
    const fieldNames = Object.keys(records[0] || {});
    const aliasMap = AppState.fieldAliases[tableId] || {};
    const headerHtml = `<thead><tr>${fieldNames.map(name =>
        `<th class="sortable-header" data-field-name="${name}">${sanitizeHTML(aliasMap[name] || name)}</th>`
    ).join('')}</tr></thead>`;
    const bodyHtml = `<tbody>${records.map(row =>
        `<tr>${fieldNames.map(name => `<td>${sanitizeHTML(row[name])}</td>`).join('')}</tr>`
    ).join('')}</tbody>`;
    return `<table class="table table-striped table-sm">${headerHtml}${bodyHtml}</table>`;
}
function renderGraphView(results) {
    if (AppState.networkInstance) {
        AppState.networkInstance.destroy();
        AppState.networkInstance = null;
    }
    DOMElements.graphContainer.innerHTML = '';
    const resultTableIds = Object.keys(results);
    const nodes = resultTableIds.filter(tableId => results[tableId].length > 0).map(tableId => ({
        id: tableId,
        label: `${CONFIG.layers[tableId].name}\n(${results[tableId].length} records)`,
        title: "Click to view records",
        shape: 'box',
        margin: 10,
        color: AppState.startTableIds.has(tableId) ? '#0d6efd' : '#6c757d',
        font: { color: '#fff' }
    }));
    const edges = [];
    const activeNodeIds = new Set(nodes.map(n => n.id));
    const checkedToggles = DOMElements.relationshipToggles.querySelectorAll('input:checked');
    const activeRelationshipIndices = Array.from(checkedToggles).map(input => parseInt(input.value, 10));
    const activeRelationships = CONFIG.relationships.filter((_, index) => activeRelationshipIndices.includes(index));
    activeRelationships.forEach((rel, index) => {
        if (activeNodeIds.has(rel.from) && activeNodeIds.has(rel.to)) {
            const fromAlias = AppState.fieldAliases[rel.from]?.[rel.fromField] || rel.fromField;
            const toAlias = AppState.fieldAliases[rel.to]?.[rel.toField] || rel.toField;
            edges.push({
                id: `edge-${CONFIG.relationships.indexOf(rel)}`, from: rel.from, to: rel.to, arrows: 'to',
                label: `${sanitizeHTML(fromAlias)} → ${sanitizeHTML(toAlias)}`,
                font: { align: 'horizontal' },
                color: { color: '#6c757d' }
            });
        }
    });
    if (nodes.length > 0 && edges.length === 0 && nodes.length > 1) {
        DOMElements.graphContainer.innerHTML = `
            <div class="alert alert-warning h-100 d-flex align-items-center justify-content-center">
                <div><h4 class="alert-heading">No Relationships to Display</h4><p>The graph view is not available because the found records have no direct relationships with each other based on the active toggles.</p></div>
            </div>`;
        return;
    }
    if (nodes.length === 0) {
         DOMElements.graphContainer.innerHTML = `<div class="alert alert-info">No records to display in the graph.</div>`;
         return;
    }
    const data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
    const options = {
        layout: { hierarchical: { enabled: true, direction: 'LR', sortMethod: 'directed', nodeSpacing: 280, levelSeparation: 400 }},
        physics: { enabled: false },
        interaction: { hover: true, hoverConnectedEdges: true, navigationButtons: true, keyboard: true },
        nodes: { shapeProperties: { borderRadius: 4 } },
        edges: { smooth: { type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.8 }, font: { size: 12, color: '#444', strokeWidth: 0, background: '#ffffff' }}
    };
    AppState.networkInstance = new vis.Network(DOMElements.graphContainer, data, options);
    AppState.networkInstance.fit({ padding: { top: 40, right: 40, bottom: 40, left: 40 }, animation: true });
    AppState.networkInstance.on('click', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const records = AppState.currentResults[nodeId];
            DOMElements.nodeModalTitle.textContent = `Records for: ${CONFIG.layers[nodeId].name}`;
            DOMElements.nodeModalBody.innerHTML = '';
            DOMElements.nodeModalBody.appendChild(createInteractiveTableContainer(records, nodeId));
            nodeModalInstance.show();
        }
    });
}
function handleTableSearch(e) {
    const input = e.target;
    if (!input.classList.contains('table-search-input')) return;
    const rawSearchTerm = input.value.toLowerCase();
    const keywords = rawSearchTerm.split(' ').filter(k => k);
    const tableId = input.dataset.targetTable;
    const table = document.getElementById(tableId);
    if (!table) return;
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(row => {
        const rowText = row.textContent.toLowerCase();
        const isMatch = keywords.every(keyword => rowText.includes(keyword));
        row.style.display = isMatch ? '' : 'none';
    });
}
function handleTableSort(e) {
    const th = e.target.closest('.sortable-header');
    if (!th) return;
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const fieldName = th.dataset.fieldName;
    const columnIndex = [...th.parentElement.children].indexOf(th);
    const currentSort = table.dataset.sortField;
    const currentDir = table.dataset.sortDir || 'asc';
    let newDir = 'asc';
    if (currentSort === fieldName && currentDir === 'asc') {
        newDir = 'desc';
    }
    table.dataset.sortField = fieldName;
    table.dataset.sortDir = newDir;
    table.querySelectorAll('.sortable-header').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
    th.classList.add(newDir === 'asc' ? 'sort-asc' : 'sort-desc');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((rowA, rowB) => {
        const valA = rowA.children[columnIndex].textContent.trim();
        const valB = rowB.children[columnIndex].textContent.trim();
        const numA = parseFloat(valA);
        const numB = parseFloat(valB);
        let comparison = 0;
        if (!isNaN(numA) && !isNaN(numB)) {
            comparison = numA - numB;
        } else {
            comparison = valA.localeCompare(valB, undefined, { numeric: true, sensitivity: 'base' });
        }
        return newDir === 'asc' ? comparison : -comparison;
    });
    tbody.innerHTML = '';
    rows.forEach(row => tbody.appendChild(row));
}
function addTableInteractionHandlers(container) {
    container.addEventListener('input', handleTableSearch);
    container.addEventListener('click', handleTableSort);
}
function init() {
    DOMElements.loginButton.addEventListener('click', handleLogin);
    DOMElements.passwordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleLogin();
    });
    DOMElements.clearAllButton.addEventListener('click', handleClearAll);
    DOMElements.globalSearchButton.addEventListener('click', handleGlobalSearch);
    DOMElements.globalSearchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleGlobalSearch();
    });
    DOMElements.globalSearchResultsContainer.addEventListener('change', delegateGlobalSearchEvents);
    DOMElements.startTableSelect.addEventListener('change', handleTableSelectChange);
    DOMElements.traceButton.addEventListener('click', startRelationshipTrace);
    DOMElements.orphanReportButton.addEventListener('click', generateOrphanReport);
    DOMElements.togglePaneBtn.addEventListener('click', togglePane);
    DOMElements.relationshipToggles.addEventListener('change', handleRelationshipToggle);
    DOMElements.viewTableBtn.addEventListener('click', () => switchView('table'));
    DOMElements.viewGraphBtn.addEventListener('click', () => switchView('graph'));
    addTableInteractionHandlers(DOMElements.resultsContainer);
    addTableInteractionHandlers(DOMElements.nodeModalBody);
    initPaneControls();
    nodeModalInstance = new bootstrap.Modal(DOMElements.nodeDetailsModal);
}
init();
