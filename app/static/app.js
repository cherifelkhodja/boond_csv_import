/**
 * BoondManager CSV Importer - Frontend Application
 */

// Entity configuration with required fields
const ENTITY_CONFIG = {
    projects: {
        requiredFields: ['company_id', 'type_of'],
        label: 'Projects',
        notes: []
    },
    deliveries: {
        requiredFields: ['project_id', 'resource_id'],
        label: 'Deliveries',
        notes: [
            'La ressource et le projet doivent appartenir a la meme agence',
            'La ressource doit avoir un contrat actif couvrant les dates de la delivery'
        ]
    },
    orders: {
        requiredFields: ['project_id', 'reference', 'turnover_excluding_tax'],
        label: 'Orders',
        notes: []
    },
    purchases: {
        requiredFields: ['project_id', 'title', 'amount_excluding_tax'],
        label: 'Purchases',
        notes: []
    },
    resources: {
        requiredFields: ['resource_id'],
        label: 'Resources',
        notes: [
            'Met a jour le type et/ou la societe fournisseur des ressources',
            'resource_type_id: si vide, le type n\'est pas modifie',
            'resource_company_id: si vide, la societe n\'est pas modifiee',
            'Le contact de la societe est recupere automatiquement (premier contact)',
            'Si aucun contact trouve, la societe ne sera pas associee (warning)'
        ]
    },
    'resource-contracts': {
        requiredFields: ['resource_id', 'contract_typeOf', 'contract_start_date'],
        label: 'Resource Contracts',
        notes: [
            'Cree des contrats pour les ressources',
            'typeOf=0: utilise contract_monthly_salary',
            'typeOf!=0: utilise contract_daily_production_cost',
            'contract_renewal=VRAI: lie au contrat precedent (meme resource_id, par start_date)',
            'Si renouvellement sans contrat precedent: warning mais creation sans parent'
        ]
    }
};

// Store data for each entity
const entityData = {};

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    initializeTabs();
    initializeTestConnection();

    // Initialize each entity tab
    Object.keys(ENTITY_CONFIG).forEach(entity => {
        initializeEntityTab(entity);
    });
});

/**
 * Initialize tab navigation
 */
function initializeTabs() {
    const tabLinks = document.querySelectorAll('.tab-link');

    tabLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const entity = link.dataset.entity;

            // Update active tab
            tabLinks.forEach(l => l.classList.remove('active'));
            link.classList.add('active');

            // Show active content
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`tab-${entity}`).classList.add('active');
        });
    });
}

/**
 * Initialize test connection button
 */
function initializeTestConnection() {
    const btn = document.getElementById('testConnectionBtn');
    const statusDiv = document.getElementById('connectionStatus');

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>Test en cours...';

        try {
            const response = await fetch('/api/test-connection');
            const data = await response.json();

            statusDiv.classList.remove('hidden', 'success', 'error');
            statusDiv.classList.add(data.success ? 'success' : 'error');
            statusDiv.textContent = data.message;
        } catch (error) {
            statusDiv.classList.remove('hidden', 'success');
            statusDiv.classList.add('error');
            statusDiv.textContent = 'Erreur de connexion au serveur';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Tester la connexion';
        }
    });
}

/**
 * Initialize an entity tab with template content
 */
function initializeEntityTab(entity) {
    const template = document.getElementById('entity-template');
    const tabContent = document.getElementById(`tab-${entity}`);

    // Skip if tab doesn't exist in HTML
    if (!tabContent) {
        console.log(`Tab for ${entity} not found in HTML, skipping`);
        return;
    }

    const clone = template.content.cloneNode(true);

    // Set entity data attribute
    const container = clone.querySelector('.entity-container');
    container.dataset.entity = entity;

    // Set required fields display
    const requiredFieldsSpan = clone.querySelector('.required-fields');
    requiredFieldsSpan.textContent = ENTITY_CONFIG[entity].requiredFields.join(', ');

    // Display notes if any
    const notes = ENTITY_CONFIG[entity].notes || [];
    if (notes.length > 0) {
        const notesContainer = clone.querySelector('.entity-notes');
        const notesList = clone.querySelector('.notes-list');
        notes.forEach(note => {
            const li = document.createElement('li');
            li.textContent = note;
            notesList.appendChild(li);
        });
        notesContainer.classList.remove('hidden');
    }

    // Initialize state
    entityData[entity] = {
        headers: [],
        rows: [],
        file: null
    };

    tabContent.appendChild(clone);

    // Setup event listeners for this entity
    setupEntityEventListeners(entity, tabContent);
}

/**
 * Setup event listeners for an entity tab
 */
function setupEntityEventListeners(entity, container) {
    const dropzone = container.querySelector('.dropzone');
    const fileInput = container.querySelector('.file-input');
    const browseBtn = container.querySelector('.browse-btn');
    const selectedFileDiv = container.querySelector('.selected-file');
    const fileNameSpan = container.querySelector('.file-name');
    const clearFileBtn = container.querySelector('.clear-file-btn');
    const downloadTemplateBtn = container.querySelector('.download-template-btn');
    const addRowBtn = container.querySelector('.add-row-btn');
    const validateBtn = container.querySelector('.validate-btn');
    const importBtn = container.querySelector('.import-btn');
    const exportResultsBtn = container.querySelector('.export-results-btn');

    // Download template
    downloadTemplateBtn.addEventListener('click', () => {
        window.location.href = `/api/${entity}/template`;
    });

    // Browse button
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });

    // Dropzone click
    dropzone.addEventListener('click', () => {
        fileInput.click();
    });

    // Drag and drop events
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].name.endsWith('.csv')) {
            handleFileSelect(entity, files[0], container);
        }
    });

    // File input change
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFileSelect(entity, fileInput.files[0], container);
        }
    });

    // Clear file
    clearFileBtn.addEventListener('click', () => {
        clearFile(entity, container);
    });

    // Add row
    addRowBtn.addEventListener('click', () => {
        addEmptyRow(entity, container);
    });

    // Validate
    validateBtn.addEventListener('click', () => {
        validateData(entity, container);
    });

    // Import
    importBtn.addEventListener('click', () => {
        importData(entity, container);
    });

    // Export results
    exportResultsBtn.addEventListener('click', () => {
        exportResults(entity, container);
    });

    // Delete contracts button (only for resource-contracts)
    const deleteContractsBtn = container.querySelector('.delete-contracts-btn');
    if (entity === 'resource-contracts') {
        deleteContractsBtn.classList.remove('hidden');
        deleteContractsBtn.addEventListener('click', () => {
            deleteContracts(entity, container);
        });
    }
}

/**
 * Handle file selection
 */
async function handleFileSelect(entity, file, container) {
    entityData[entity].file = file;

    const selectedFileDiv = container.querySelector('.selected-file');
    const fileNameSpan = container.querySelector('.file-name');

    selectedFileDiv.classList.remove('hidden');
    fileNameSpan.textContent = file.name;

    // Parse CSV
    const content = await file.text();
    parseCSV(entity, content, container);
}

/**
 * Detect CSV delimiter (comma or semicolon)
 */
function detectDelimiter(firstLine) {
    const semicolons = (firstLine.match(/;/g) || []).length;
    const commas = (firstLine.match(/,/g) || []).length;
    return semicolons > commas ? ';' : ',';
}

/**
 * Parse CSV content
 */
function parseCSV(entity, content, container) {
    const lines = content.trim().split('\n');
    if (lines.length === 0) return;

    // Detect delimiter
    const delimiter = detectDelimiter(lines[0]);
    entityData[entity].delimiter = delimiter;

    // Parse headers
    const headers = lines[0].split(delimiter).map(h => h.trim());
    entityData[entity].headers = headers;

    // Parse rows
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
        const values = parseCSVLine(lines[i], delimiter);
        if (values.length > 0) {
            const row = {};
            headers.forEach((header, index) => {
                row[header] = values[index] || '';
            });
            rows.push(row);
        }
    }
    entityData[entity].rows = rows;

    // Render preview
    renderPreview(entity, container);

    // Show sections
    container.querySelector('.preview-section').classList.remove('hidden');
    container.querySelector('.actions-section').classList.remove('hidden');
}

/**
 * Parse a single CSV line (handling quoted values)
 */
function parseCSVLine(line, delimiter = ',') {
    const result = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
        const char = line[i];

        if (char === '"') {
            if (inQuotes && line[i + 1] === '"') {
                // Escaped quote inside quoted string
                current += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (char === delimiter && !inQuotes) {
            result.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    result.push(current.trim());

    return result;
}

/**
 * Render the preview table
 */
function renderPreview(entity, container) {
    const thead = container.querySelector('.preview-table thead');
    const tbody = container.querySelector('.preview-table tbody');
    const headers = entityData[entity].headers;
    const rows = entityData[entity].rows;
    const requiredFields = ENTITY_CONFIG[entity].requiredFields;

    // Render headers
    thead.innerHTML = '<tr>' +
        headers.map(h => `<th class="${requiredFields.includes(h) ? 'required' : ''}">${h}</th>`).join('') +
        '<th></th></tr>';

    // Render rows
    tbody.innerHTML = '';
    rows.forEach((row, rowIndex) => {
        const tr = document.createElement('tr');
        tr.innerHTML = headers.map(h =>
            `<td><input type="text" value="${escapeHtml(row[h] || '')}" data-field="${h}" data-row="${rowIndex}"></td>`
        ).join('') +
        `<td><button class="delete-row-btn" data-row="${rowIndex}">&times;</button></td>`;

        // Add input event listeners
        tr.querySelectorAll('input').forEach(input => {
            input.addEventListener('input', (e) => {
                const field = e.target.dataset.field;
                const rowIdx = parseInt(e.target.dataset.row);
                entityData[entity].rows[rowIdx][field] = e.target.value;
            });
        });

        // Add delete button listener
        tr.querySelector('.delete-row-btn').addEventListener('click', (e) => {
            const rowIdx = parseInt(e.target.dataset.row);
            entityData[entity].rows.splice(rowIdx, 1);
            renderPreview(entity, container);
        });

        tbody.appendChild(tr);
    });
}

/**
 * Add an empty row
 */
function addEmptyRow(entity, container) {
    const headers = entityData[entity].headers;
    if (headers.length === 0) {
        // Fetch headers from API if not loaded
        fetchFieldsAndAddRow(entity, container);
        return;
    }

    const newRow = {};
    headers.forEach(h => newRow[h] = '');
    entityData[entity].rows.push(newRow);
    renderPreview(entity, container);
}

/**
 * Fetch fields from API and add a row
 */
async function fetchFieldsAndAddRow(entity, container) {
    try {
        const response = await fetch(`/api/${entity}/fields`);
        const data = await response.json();

        entityData[entity].headers = data.fields;

        const newRow = {};
        data.fields.forEach(f => newRow[f] = '');
        entityData[entity].rows.push(newRow);

        renderPreview(entity, container);
        container.querySelector('.preview-section').classList.remove('hidden');
        container.querySelector('.actions-section').classList.remove('hidden');
    } catch (error) {
        console.error('Error fetching fields:', error);
    }
}

/**
 * Clear the selected file
 */
function clearFile(entity, container) {
    entityData[entity] = {
        headers: [],
        rows: [],
        file: null
    };

    container.querySelector('.selected-file').classList.add('hidden');
    container.querySelector('.file-input').value = '';
    container.querySelector('.preview-section').classList.add('hidden');
    container.querySelector('.actions-section').classList.add('hidden');
    container.querySelector('.results-section').classList.add('hidden');
    container.querySelector('.validation-errors').classList.add('hidden');
}

/**
 * Validate data locally and via API
 */
async function validateData(entity, container) {
    const validateBtn = container.querySelector('.validate-btn');
    const validationErrors = container.querySelector('.validation-errors');
    const errorList = container.querySelector('.error-list');

    validateBtn.disabled = true;
    validateBtn.innerHTML = '<span class="spinner"></span>Validation...';

    // Clear previous errors
    validationErrors.classList.add('hidden');
    errorList.innerHTML = '';

    // Clear input error styles
    container.querySelectorAll('input.error').forEach(input => {
        input.classList.remove('error');
    });

    try {
        // Create CSV from current data
        const csvContent = createCSVFromData(entity);
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const formData = new FormData();
        formData.append('file', blob, 'data.csv');

        const response = await fetch(`/api/${entity}/validate`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.valid) {
            showNotification('Validation reussie ! Pret pour l\'import.', 'success');
        } else {
            // Show errors
            validationErrors.classList.remove('hidden');
            result.errors.forEach(error => {
                const li = document.createElement('li');
                li.textContent = `Ligne ${error.row}: ${error.field} - ${error.error}`;
                errorList.appendChild(li);

                // Highlight error cells
                const input = container.querySelector(
                    `input[data-row="${error.row - 1}"][data-field="${error.field}"]`
                );
                if (input) {
                    input.classList.add('error');
                }
            });
        }
    } catch (error) {
        showNotification('Erreur lors de la validation', 'error');
    } finally {
        validateBtn.disabled = false;
        validateBtn.textContent = 'Valider';
    }
}

/**
 * Import data to BoondManager
 */
async function importData(entity, container) {
    const importBtn = container.querySelector('.import-btn');
    const progressContainer = container.querySelector('.progress-container');
    const progressFill = container.querySelector('.progress-fill');
    const progressText = container.querySelector('.progress-text');
    const resultsSection = container.querySelector('.results-section');
    const resultsTbody = container.querySelector('.results-table tbody');
    const successCount = container.querySelector('.success-count');
    const failedCount = container.querySelector('.failed-count');

    importBtn.disabled = true;
    importBtn.innerHTML = '<span class="spinner"></span>Import en cours...';
    progressContainer.classList.remove('hidden');
    progressFill.style.width = '0%';
    progressText.textContent = '0%';

    try {
        // Create CSV from current data
        const csvContent = createCSVFromData(entity);
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const formData = new FormData();
        formData.append('file', blob, 'data.csv');

        // Simulate progress for UX
        let progress = 0;
        const progressInterval = setInterval(() => {
            if (progress < 90) {
                progress += 5;
                progressFill.style.width = `${progress}%`;
                progressText.textContent = `${progress}%`;
            }
        }, 200);

        const response = await fetch(`/api/${entity}/import`, {
            method: 'POST',
            body: formData
        });

        clearInterval(progressInterval);
        progressFill.style.width = '100%';
        progressText.textContent = '100%';

        const result = await response.json();

        // Store results for export
        entityData[entity].importResults = result;

        // Display results
        displayResults(entity, container, result);

        if (result.failed === 0) {
            showNotification(`Import termine avec succes ! ${result.success} elements crees.`, 'success');
        } else {
            showNotification(`Import termine avec ${result.failed} erreur(s).`, 'warning');
        }
    } catch (error) {
        showNotification('Erreur lors de l\'import', 'error');
    } finally {
        importBtn.disabled = false;
        importBtn.textContent = 'Importer';
    }
}

/**
 * Export import results to CSV
 */
function exportResults(entity, container) {
    const results = entityData[entity].importResults;
    if (!results || !results.results.length) return;

    // Get original headers from the first result's original_data
    const firstResult = results.results[0];
    const originalHeaders = firstResult.original_data ? Object.keys(firstResult.original_data) : [];

    // Build entity-specific ID column name (projects -> project_id, deliveries -> delivery_id)
    const entityIdName = entity.replace(/s$/, '') + '_id';

    // Build headers: original data + entity_id + status + message
    const headers = [...originalHeaders, entityIdName, 'status', 'message'];

    // Build CSV content
    const headerLine = headers.join(';');
    const dataLines = results.results.map(r => {
        const originalValues = originalHeaders.map(h =>
            escapeCSVValue(r.original_data ? (r.original_data[h] || '') : '')
        );
        return [
            ...originalValues,
            r.id || '',
            r.status,
            escapeCSVValue(r.message || '')
        ].join(';');
    });

    const csvContent = [headerLine, ...dataLines].join('\n');
    downloadCSV(csvContent, `${entity}_import_results.csv`);
}

/**
 * Create CSV content from entity data
 */
function createCSVFromData(entity) {
    const headers = entityData[entity].headers;
    const rows = entityData[entity].rows;

    const headerLine = headers.join(',');
    const dataLines = rows.map(row =>
        headers.map(h => escapeCSVValue(row[h] || '')).join(',')
    );

    return [headerLine, ...dataLines].join('\n');
}

/**
 * Escape a value for CSV
 */
function escapeCSVValue(value) {
    if (value.includes(',') || value.includes('"') || value.includes('\n')) {
        return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
}

/**
 * Escape HTML characters
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Download CSV file
 */
function downloadCSV(content, filename) {
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
}

/**
 * Show notification
 */
function showNotification(message, type) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    // Style it
    Object.assign(notification.style, {
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        padding: '1rem 1.5rem',
        borderRadius: '8px',
        fontWeight: '500',
        zIndex: '1000',
        animation: 'slideIn 0.3s ease'
    });

    if (type === 'success') {
        notification.style.backgroundColor = '#ecfdf5';
        notification.style.color = '#10b981';
        notification.style.border = '1px solid #10b981';
    } else if (type === 'error') {
        notification.style.backgroundColor = '#fef2f2';
        notification.style.color = '#ef4444';
        notification.style.border = '1px solid #ef4444';
    } else if (type === 'warning') {
        notification.style.backgroundColor = '#fffbeb';
        notification.style.color = '#f59e0b';
        notification.style.border = '1px solid #f59e0b';
    }

    document.body.appendChild(notification);

    // Remove after 3 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

/**
 * Display results in the results section
 */
function displayResults(entity, container, result) {
    const resultsSection = container.querySelector('.results-section');
    const resultsTbody = container.querySelector('.results-table tbody');
    const successCount = container.querySelector('.success-count');
    const failedCount = container.querySelector('.failed-count');

    resultsSection.classList.remove('hidden');
    successCount.textContent = `Succes: ${result.success}`;
    failedCount.textContent = `Echecs: ${result.failed}`;

    resultsTbody.innerHTML = '';
    result.results.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${r.row}</td>
            <td class="status-${r.status}">${r.status === 'success' ? 'Succes' : 'Erreur'}</td>
            <td>${r.id || '-'}</td>
            <td>${escapeHtml(r.message || '-')}</td>
        `;
        resultsTbody.appendChild(tr);
    });
}

/**
 * Delete contracts for resources in CSV
 */
async function deleteContracts(entity, container) {
    const file = entityData[entity].file;
    if (!file) {
        // Try to create from data
        const csvContent = createCSVFromData(entity);
        if (!csvContent || entityData[entity].rows.length === 0) {
            showNotification('Veuillez d\'abord charger un fichier CSV', 'error');
            return;
        }
    }

    const deleteBtn = container.querySelector('.delete-contracts-btn');
    deleteBtn.disabled = true;
    deleteBtn.innerHTML = '<span class="spinner"></span>Analyse...';

    try {
        // First, preview what will be deleted
        const csvContent = createCSVFromData(entity);
        const blob = new Blob([csvContent], { type: 'text/csv' });
        const formData = new FormData();
        formData.append('file', blob, 'data.csv');

        const previewResponse = await fetch(`/api/${entity}/preview-delete`, {
            method: 'POST',
            body: formData
        });

        const preview = await previewResponse.json();

        deleteBtn.disabled = false;
        deleteBtn.textContent = 'Supprimer les contrats';

        // Show confirmation dialog
        const confirmMessage = `Êtes-vous sûr de vouloir supprimer ${preview.total_contracts} contrat(s) pour ${preview.total_resources} ressource(s) ?\n\nCette action est irréversible.`;

        if (!confirm(confirmMessage)) {
            showNotification('Suppression annulée', 'warning');
            return;
        }

        // Proceed with deletion
        deleteBtn.disabled = true;
        deleteBtn.innerHTML = '<span class="spinner"></span>Suppression...';

        const deleteFormData = new FormData();
        deleteFormData.append('file', blob, 'data.csv');

        const deleteResponse = await fetch(`/api/${entity}/delete-contracts`, {
            method: 'POST',
            body: deleteFormData
        });

        const result = await deleteResponse.json();

        // Store results
        entityData[entity].importResults = result;

        // Show results
        displayResults(entity, container, result);

        if (result.failed === 0) {
            showNotification(`${result.success} ressource(s) traitée(s) avec succès`, 'success');
        } else {
            showNotification(`${result.success} succès, ${result.failed} erreur(s)`, 'warning');
        }

    } catch (error) {
        console.error('Error deleting contracts:', error);
        showNotification('Erreur lors de la suppression', 'error');
    } finally {
        deleteBtn.disabled = false;
        deleteBtn.textContent = 'Supprimer les contrats';
    }
}

// Add animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

/**
 * Export Time Reports functionality
 */
const exportTimeReports = {
    file: null,
    csvContent: null,
    headers: [],
    rows: [],

    init() {
        const dropzone = document.getElementById('export-tr-dropzone');
        const fileInput = document.getElementById('export-tr-file-input');
        const browseBtn = document.getElementById('export-tr-browse-btn');
        const clearBtn = document.getElementById('export-tr-clear-btn');
        const startBtn = document.getElementById('export-tr-start-btn');
        const downloadBtn = document.getElementById('export-tr-download-btn');

        if (!dropzone) return; // Tab not present

        // Browse button
        browseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });

        // Dropzone click
        dropzone.addEventListener('click', () => {
            fileInput.click();
        });

        // Drag and drop
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0 && files[0].name.endsWith('.csv')) {
                this.handleFileSelect(files[0]);
            }
        });

        // File input change
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                this.handleFileSelect(fileInput.files[0]);
            }
        });

        // Clear file
        clearBtn.addEventListener('click', () => {
            this.clearFile();
        });

        // Start export
        startBtn.addEventListener('click', () => {
            this.startExport();
        });

        // Download CSV
        downloadBtn.addEventListener('click', () => {
            this.downloadCSV();
        });
    },

    async handleFileSelect(file) {
        this.file = file;
        document.getElementById('export-tr-selected-file').classList.remove('hidden');
        document.getElementById('export-tr-file-name').textContent = file.name;

        // Parse CSV and show preview
        const content = await file.text();
        this.parseAndPreview(content);
    },

    parseAndPreview(content) {
        const lines = content.trim().split('\n');
        if (lines.length === 0) return;

        // Detect delimiter
        const firstLine = lines[0];
        const semicolons = (firstLine.match(/;/g) || []).length;
        const commas = (firstLine.match(/,/g) || []).length;
        const delimiter = semicolons > commas ? ';' : ',';

        // Parse headers
        this.headers = lines[0].split(delimiter).map(h => h.trim());

        // Parse rows
        this.rows = [];
        for (let i = 1; i < lines.length; i++) {
            const values = this.parseCSVLine(lines[i], delimiter);
            if (values.length > 0 && values.some(v => v.trim() !== '')) {
                const row = {};
                this.headers.forEach((header, index) => {
                    row[header] = values[index] || '';
                });
                this.rows.push(row);
            }
        }

        // Render preview
        this.renderPreview();

        // Enable start button if we have resource_id column and rows
        const hasResourceId = this.headers.some(h => h.toLowerCase() === 'resource_id');
        document.getElementById('export-tr-start-btn').disabled = !hasResourceId || this.rows.length === 0;

        if (!hasResourceId) {
            showNotification('Le fichier doit contenir une colonne resource_id', 'error');
        }
    },

    parseCSVLine(line, delimiter = ',') {
        const result = [];
        let current = '';
        let inQuotes = false;

        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            if (char === '"') {
                if (inQuotes && line[i + 1] === '"') {
                    current += '"';
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (char === delimiter && !inQuotes) {
                result.push(current.trim());
                current = '';
            } else {
                current += char;
            }
        }
        result.push(current.trim());
        return result;
    },

    renderPreview() {
        const previewSection = document.getElementById('export-tr-preview-section');
        const table = document.getElementById('export-tr-preview-table');
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const rowCount = document.getElementById('export-tr-row-count');

        // Update row count
        rowCount.textContent = this.rows.length;

        // Render headers (with action column)
        thead.innerHTML = '<tr>' + this.headers.map(h => {
            const isResourceId = h.toLowerCase() === 'resource_id';
            return `<th class="${isResourceId ? 'required' : ''}">${escapeHtml(h)}</th>`;
        }).join('') + '<th class="action-col">Actions</th></tr>';

        // Render rows (limit to 100 for performance)
        const displayRows = this.rows.slice(0, 100);
        tbody.innerHTML = displayRows.map((row, index) => {
            return '<tr data-index="' + index + '">' +
                this.headers.map(h => `<td>${escapeHtml(row[h] || '')}</td>`).join('') +
                `<td class="action-col"><button class="btn-delete-row" onclick="exportTimeReports.deleteRow(${index})" title="Supprimer cette ligne">✕</button></td>` +
                '</tr>';
        }).join('');

        // Show warning if more than 100 rows
        if (this.rows.length > 100) {
            const warning = document.createElement('div');
            warning.className = 'preview-warning';
            warning.textContent = `Affichage limité à 100 lignes sur ${this.rows.length}. Toutes les lignes seront exportées.`;
            tbody.parentNode.insertAdjacentElement('afterend', warning);
        }

        // Show preview section
        previewSection.classList.remove('hidden');

        // Update start button state
        document.getElementById('export-tr-start-btn').disabled = this.rows.length === 0;
    },

    deleteRow(index) {
        if (index >= 0 && index < this.rows.length) {
            this.rows.splice(index, 1);
            this.renderPreview();
            showNotification('Ligne supprimée', 'info');
        }
    },

    clearFile() {
        this.file = null;
        this.csvContent = null;
        this.headers = [];
        this.rows = [];
        document.getElementById('export-tr-selected-file').classList.add('hidden');
        document.getElementById('export-tr-file-input').value = '';
        document.getElementById('export-tr-start-btn').disabled = true;
        document.getElementById('export-tr-preview-section').classList.add('hidden');
        document.getElementById('export-tr-progress').classList.add('hidden');
        document.getElementById('export-tr-results').classList.add('hidden');
        document.getElementById('export-tr-action-log').innerHTML = '';
    },

    async startExport() {
        if (!this.file) return;

        const startBtn = document.getElementById('export-tr-start-btn');
        const progressContainer = document.getElementById('export-tr-progress');
        const progressFill = document.getElementById('export-tr-progress-fill');
        const progressText = document.getElementById('export-tr-progress-text');
        const progressAction = document.getElementById('export-tr-progress-action');
        const actionLog = document.getElementById('export-tr-action-log');
        const resultsSection = document.getElementById('export-tr-results');

        startBtn.disabled = true;
        startBtn.innerHTML = '<span class="spinner"></span>Export en cours...';
        progressContainer.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        progressAction.textContent = '';
        actionLog.innerHTML = '';

        try {
            // Generate CSV from modified rows (in case user deleted some)
            const csvLines = [this.headers.join(',')];
            for (const row of this.rows) {
                const values = this.headers.map(h => {
                    const val = row[h] || '';
                    // Escape values with comma, quote, or newline
                    if (val.includes(',') || val.includes('"') || val.includes('\n')) {
                        return `"${val.replace(/"/g, '""')}"`;
                    }
                    return val;
                });
                csvLines.push(values.join(','));
            }
            const csvContent = csvLines.join('\n');
            const csvBlob = new Blob([csvContent], { type: 'text/csv' });
            const csvFile = new File([csvBlob], 'export.csv', { type: 'text/csv' });

            const formData = new FormData();
            formData.append('file', csvFile);

            const url = `/api/export-time-reports/export`;

            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Process complete lines (SSE messages end with \n\n)
                const messages = buffer.split('\n\n');
                // Keep incomplete message in buffer
                buffer = messages.pop() || '';

                for (const message of messages) {
                    const lines = message.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                this.handleSSEEvent(data);
                            } catch (e) {
                                console.error('Error parsing SSE:', e, line.substring(0, 100));
                            }
                        }
                    }
                }
            }

            // Process any remaining buffer
            if (buffer.trim()) {
                const lines = buffer.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            this.handleSSEEvent(data);
                        } catch (e) {
                            console.error('Error parsing final SSE:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Export error:', error);
            showNotification('Erreur lors de l\'export', 'error');
        } finally {
            startBtn.disabled = false;
            startBtn.textContent = 'Lancer l\'export';
        }
    },

    handleSSEEvent(data) {
        const progressFill = document.getElementById('export-tr-progress-fill');
        const progressText = document.getElementById('export-tr-progress-text');
        const progressAction = document.getElementById('export-tr-progress-action');
        const actionLog = document.getElementById('export-tr-action-log');
        const resultsSection = document.getElementById('export-tr-results');
        const successCount = document.getElementById('export-tr-success-count');
        const entriesCount = document.getElementById('export-tr-entries-count');

        switch (data.type) {
            case 'progress':
                progressFill.style.width = `${data.percent}%`;
                progressText.textContent = `${data.percent}% (${data.current}/${data.total})`;
                progressAction.textContent = data.action;
                break;

            case 'action':
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry';
                if (data.message.startsWith('ERROR')) {
                    logEntry.classList.add('error');
                } else if (data.message.includes('exportees')) {
                    logEntry.classList.add('success');
                }
                logEntry.textContent = data.message;
                actionLog.appendChild(logEntry);
                actionLog.scrollTop = actionLog.scrollHeight;
                break;

            case 'complete':
                progressFill.style.width = '100%';
                progressText.textContent = '100%';

                // Store CSV content
                this.csvContent = data.csv_content;

                // Show results
                resultsSection.classList.remove('hidden');
                successCount.textContent = `Resources traitees: ${data.success}/${data.total}`;
                entriesCount.textContent = `Entrees exportees: ${data.total_entries}`;

                // Render output CSV preview
                this.renderOutputPreview(data.csv_content);

                if (data.failed === 0) {
                    showNotification(`Export termine ! ${data.total_entries} entrees exportees.`, 'success');
                } else {
                    showNotification(`Export termine avec ${data.failed} erreur(s).`, 'warning');
                }
                break;
        }
    },

    renderOutputPreview(csvContent) {
        if (!csvContent) return;

        const table = document.getElementById('export-tr-output-table');
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        const lines = csvContent.trim().split('\n');
        if (lines.length === 0) return;

        // Parse headers
        const headers = this.parseCSVLine(lines[0], ',');

        // Render headers
        thead.innerHTML = '<tr>' + headers.map(h => `<th>${escapeHtml(h)}</th>`).join('') + '</tr>';

        // Parse and render rows (limit to 100 for performance)
        const maxRows = Math.min(lines.length - 1, 100);
        let rowsHtml = '';
        for (let i = 1; i <= maxRows; i++) {
            const values = this.parseCSVLine(lines[i], ',');
            rowsHtml += '<tr>' + values.map(v => `<td>${escapeHtml(v)}</td>`).join('') + '</tr>';
        }
        tbody.innerHTML = rowsHtml;

        if (lines.length - 1 > 100) {
            tbody.innerHTML += `<tr><td colspan="${headers.length}" style="text-align:center;color:var(--text-light);">... et ${lines.length - 101} autres lignes</td></tr>`;
        }
    },

    downloadCSV() {
        if (!this.csvContent) {
            showNotification('Aucun contenu a telecharger', 'error');
            return;
        }

        const today = new Date().toISOString().split('T')[0];
        const filename = `time_reports_export_${today}.csv`;

        const blob = new Blob([this.csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
    }
};

// Import Time Reports functionality
const importTimeReports = {
    file: null,
    headers: [],
    rows: [],
    deliveriesFile: null,
    deliveries: [],
    unmatchedRows: [],

    init() {
        const dropzone = document.getElementById('import-tr-dropzone');
        const fileInput = document.getElementById('import-tr-file-input');
        const browseBtn = document.getElementById('import-tr-browse-btn');
        const clearBtn = document.getElementById('import-tr-clear-btn');
        const startBtn = document.getElementById('import-tr-start-btn');

        // Deliveries dropzone
        const deliveriesDropzone = document.getElementById('import-tr-deliveries-dropzone');
        const deliveriesFileInput = document.getElementById('import-tr-deliveries-file-input');
        const deliveriesBrowseBtn = document.getElementById('import-tr-deliveries-browse-btn');
        const deliveriesClearBtn = document.getElementById('import-tr-deliveries-clear-btn');

        if (!dropzone) return;

        // Deliveries drag and drop handlers
        deliveriesDropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            deliveriesDropzone.classList.add('dragover');
        });
        deliveriesDropzone.addEventListener('dragleave', () => {
            deliveriesDropzone.classList.remove('dragover');
        });
        deliveriesDropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            deliveriesDropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this.handleDeliveriesFileSelect(e.dataTransfer.files[0]);
            }
        });
        deliveriesBrowseBtn.addEventListener('click', () => deliveriesFileInput.click());
        deliveriesFileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleDeliveriesFileSelect(e.target.files[0]);
            }
        });
        deliveriesClearBtn.addEventListener('click', () => this.clearDeliveriesFile());

        // Time reports drag and drop handlers
        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });
        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0) {
                this.handleFileSelect(e.dataTransfer.files[0]);
            }
        });
        browseBtn.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileSelect(e.target.files[0]);
            }
        });
        clearBtn.addEventListener('click', () => this.clearFile());
        startBtn.addEventListener('click', () => this.startImport());
    },

    handleDeliveriesFileSelect(file) {
        if (!file.name.endsWith('.csv')) {
            showNotification('Veuillez selectionner un fichier CSV', 'error');
            return;
        }
        this.deliveriesFile = file;
        document.getElementById('import-tr-deliveries-file-name').textContent = file.name;
        document.getElementById('import-tr-deliveries-selected-file').classList.remove('hidden');
        this.parseDeliveries();
    },

    parseDeliveries() {
        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target.result;
            const lines = content.split('\n').filter(line => line.trim() !== '');
            if (lines.length < 2) {
                showNotification('Le fichier CSV des deliveries est vide', 'error');
                return;
            }
            const delimiter = lines[0].includes(';') ? ';' : ',';
            const headers = lines[0].split(delimiter).map(h => h.trim());

            // Check required columns
            const hasDeliveryId = headers.some(h => h.toLowerCase() === 'delivery_id');
            const hasResourceId = headers.some(h => h.toLowerCase() === 'resource_id');
            const hasProjectId = headers.some(h => h.toLowerCase() === 'project_id');
            const hasStartDate = headers.some(h => h.toLowerCase() === 'startdate');
            const hasEndDate = headers.some(h => h.toLowerCase() === 'enddate');

            if (!hasDeliveryId || !hasResourceId || !hasProjectId || !hasStartDate || !hasEndDate) {
                showNotification('Le CSV deliveries doit contenir: delivery_id, resource_id, project_id, startDate, endDate', 'error');
                return;
            }

            this.deliveries = [];
            for (let i = 1; i < lines.length; i++) {
                const values = this.parseCSVLine(lines[i], delimiter);
                if (values.length > 0) {
                    const row = {};
                    headers.forEach((header, index) => {
                        row[header] = values[index] || '';
                    });
                    // Normalize column names
                    const delivery = {
                        delivery_id: row.delivery_id || row.Delivery_id || row.DELIVERY_ID,
                        resource_id: row.resource_id || row.Resource_id || row.RESOURCE_ID,
                        project_id: row.project_id || row.Project_id || row.PROJECT_ID,
                        startDate: this.parseDate(row.startDate || row.StartDate || row.STARTDATE),
                        endDate: this.parseDate(row.endDate || row.EndDate || row.ENDDATE),
                    };
                    if (delivery.delivery_id && delivery.resource_id && delivery.startDate && delivery.endDate) {
                        this.deliveries.push(delivery);
                    }
                }
            }

            const countEl = document.getElementById('import-tr-deliveries-count');
            countEl.textContent = `${this.deliveries.length} deliveries chargees`;
            countEl.classList.remove('hidden');
            showNotification(`${this.deliveries.length} deliveries chargees`, 'success');
            this.updateStartButton();
            // Re-match if time reports already loaded
            if (this.rows.length > 0) {
                this.matchDeliveries();
                this.renderPreview();
            }
        };
        reader.readAsText(this.deliveriesFile);
    },

    parseDate(dateStr) {
        if (!dateStr) return null;
        // Handle DD/MM/YYYY format
        if (dateStr.includes('/')) {
            const parts = dateStr.split('/');
            if (parts.length === 3) {
                return new Date(parts[2], parts[1] - 1, parts[0]);
            }
        }
        // Handle YYYY-MM-DD format
        return new Date(dateStr);
    },

    formatDateForAPI(date) {
        if (!date) return '';
        const d = new Date(date);
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    },

    handleFileSelect(file) {
        if (!file.name.endsWith('.csv')) {
            showNotification('Veuillez selectionner un fichier CSV', 'error');
            return;
        }
        this.file = file;
        document.getElementById('import-tr-file-name').textContent = file.name;
        document.getElementById('import-tr-selected-file').classList.remove('hidden');
        this.parseAndPreview();
    },

    parseAndPreview() {
        const reader = new FileReader();
        reader.onload = (e) => {
            const content = e.target.result;
            const lines = content.split('\n').filter(line => line.trim() !== '');
            if (lines.length < 2) {
                showNotification('Le fichier CSV est vide ou invalide', 'error');
                return;
            }
            const delimiter = lines[0].includes(';') ? ';' : ',';
            this.headers = lines[0].split(delimiter).map(h => h.trim());

            // Check required columns
            const hasResourceId = this.headers.some(h => h.toLowerCase() === 'resource_id');
            const hasTerm = this.headers.some(h => h.toLowerCase() === 'term');
            const hasStartDate = this.headers.some(h => h.toLowerCase() === 'startdate');

            if (!hasResourceId || !hasTerm || !hasStartDate) {
                showNotification('Le fichier doit contenir: resource_id, term, startDate', 'error');
                return;
            }

            this.rows = [];
            for (let i = 1; i < lines.length; i++) {
                const values = this.parseCSVLine(lines[i], delimiter);
                if (values.length > 0 && values.some(v => v.trim() !== '')) {
                    const row = {};
                    this.headers.forEach((header, index) => {
                        row[header] = values[index] || '';
                    });
                    this.rows.push(row);
                }
            }

            // Add project_id and delivery_id columns if not present
            if (!this.headers.includes('project_id')) this.headers.push('project_id');
            if (!this.headers.includes('delivery_id')) this.headers.push('delivery_id');

            // Match deliveries
            this.matchDeliveries();
            this.renderPreview();
            this.updateStartButton();
        };
        reader.readAsText(this.file);
    },

    matchDeliveries() {
        this.unmatchedRows = [];
        for (const row of this.rows) {
            const resourceId = row.resource_id || row.Resource_id || row.RESOURCE_ID;
            const startDateStr = row.startDate || row.StartDate || row.STARTDATE;
            const entryDate = this.parseDate(startDateStr);

            if (!entryDate || !resourceId) {
                row.project_id = '';
                row.delivery_id = '';
                row._matchStatus = 'error';
                this.unmatchedRows.push(row);
                continue;
            }

            // Find matching delivery
            const matchingDelivery = this.deliveries.find(d => {
                return d.resource_id === resourceId &&
                    entryDate >= d.startDate &&
                    entryDate <= d.endDate;
            });

            if (matchingDelivery) {
                row.project_id = matchingDelivery.project_id;
                row.delivery_id = matchingDelivery.delivery_id;
                row._matchStatus = 'matched';
            } else {
                row.project_id = '';
                row.delivery_id = '';
                row._matchStatus = 'unmatched';
                this.unmatchedRows.push(row);
            }
        }

        if (this.unmatchedRows.length > 0) {
            showNotification(`${this.unmatchedRows.length} lignes sans delivery correspondante`, 'warning');
        }
    },

    updateStartButton() {
        const hasDeliveries = this.deliveries.length > 0;
        const hasRows = this.rows.length > 0;
        const hasMatched = this.rows.some(r => r._matchStatus === 'matched');
        document.getElementById('import-tr-start-btn').disabled = !hasDeliveries || !hasRows || !hasMatched;
    },

    parseCSVLine(line, delimiter = ',') {
        const result = [];
        let current = '';
        let inQuotes = false;

        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            if (char === '"') {
                if (inQuotes && line[i + 1] === '"') {
                    current += '"';
                    i++;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (char === delimiter && !inQuotes) {
                result.push(current.trim());
                current = '';
            } else {
                current += char;
            }
        }
        result.push(current.trim());
        return result;
    },

    renderPreview() {
        const previewSection = document.getElementById('import-tr-preview-section');
        const table = document.getElementById('import-tr-preview-table');
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const rowCount = document.getElementById('import-tr-row-count');
        const reportCount = document.getElementById('import-tr-report-count');

        // Count matched rows
        const matchedRows = this.rows.filter(r => r._matchStatus === 'matched');
        rowCount.textContent = `${matchedRows.length}/${this.rows.length}`;

        // Calculate unique resource_id + term combinations from matched rows
        const uniqueReports = new Set();
        matchedRows.forEach(row => {
            const resourceId = row.resource_id || row.Resource_id || row.RESOURCE_ID;
            const term = row.term || row.Term || row.TERM;
            const key = `${resourceId}_${term}`;
            uniqueReports.add(key);
        });
        reportCount.textContent = uniqueReports.size;

        // Render headers (with status and action columns)
        const displayHeaders = this.headers.filter(h => !h.startsWith('_'));
        thead.innerHTML = '<tr><th>Status</th>' + displayHeaders.map(h => {
            const lh = h.toLowerCase();
            const isRequired = lh === 'resource_id' || lh === 'term' || lh === 'startdate' || lh === 'project_id' || lh === 'delivery_id';
            return `<th class="${isRequired ? 'required' : ''}">${escapeHtml(h)}</th>`;
        }).join('') + '<th class="action-col">Actions</th></tr>';

        // Render rows (limit to 100 for performance)
        const displayRows = this.rows.slice(0, 100);
        tbody.innerHTML = displayRows.map((row, index) => {
            const statusClass = row._matchStatus === 'matched' ? 'status-success' : 'status-error';
            const statusText = row._matchStatus === 'matched' ? '✓' : '✗';
            return `<tr data-index="${index}" class="${row._matchStatus !== 'matched' ? 'row-unmatched' : ''}">` +
                `<td class="${statusClass}">${statusText}</td>` +
                displayHeaders.map(h => `<td>${escapeHtml(row[h] || '')}</td>`).join('') +
                `<td class="action-col"><button class="btn-delete-row" onclick="importTimeReports.deleteRow(${index})" title="Supprimer cette ligne">✕</button></td>` +
                '</tr>';
        }).join('');

        // Show warning if more than 100 rows
        if (this.rows.length > 100) {
            const warning = document.createElement('div');
            warning.className = 'preview-warning';
            warning.textContent = `Affichage limite a 100 lignes sur ${this.rows.length}. Toutes les lignes seront importees.`;
            tbody.parentNode.insertAdjacentElement('afterend', warning);
        }

        previewSection.classList.remove('hidden');
    },

    deleteRow(index) {
        if (index >= 0 && index < this.rows.length) {
            this.rows.splice(index, 1);
            this.matchDeliveries();
            this.renderPreview();
            this.updateStartButton();
            showNotification('Ligne supprimee', 'info');
        }
    },

    clearDeliveriesFile() {
        this.deliveriesFile = null;
        this.deliveries = [];
        document.getElementById('import-tr-deliveries-file-input').value = '';
        document.getElementById('import-tr-deliveries-selected-file').classList.add('hidden');
        document.getElementById('import-tr-deliveries-count').classList.add('hidden');
        // Re-match to clear project/delivery
        if (this.rows.length > 0) {
            this.matchDeliveries();
            this.renderPreview();
        }
        this.updateStartButton();
    },

    clearFile() {
        this.file = null;
        this.headers = [];
        this.rows = [];
        this.unmatchedRows = [];
        document.getElementById('import-tr-file-input').value = '';
        document.getElementById('import-tr-selected-file').classList.add('hidden');
        document.getElementById('import-tr-preview-section').classList.add('hidden');
        document.getElementById('import-tr-results').classList.add('hidden');
        this.updateStartButton();
    },

    async startImport() {
        const startBtn = document.getElementById('import-tr-start-btn');
        const progressContainer = document.getElementById('import-tr-progress');
        const progressFill = document.getElementById('import-tr-progress-fill');
        const progressText = document.getElementById('import-tr-progress-text');
        const progressAction = document.getElementById('import-tr-progress-action');
        const actionLog = document.getElementById('import-tr-action-log');
        const resultsSection = document.getElementById('import-tr-results');

        startBtn.disabled = true;
        startBtn.innerHTML = '<span class="spinner"></span>Import en cours...';
        progressContainer.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        progressAction.textContent = '';
        actionLog.innerHTML = '';

        try {
            // Generate CSV from matched rows only
            const matchedRows = this.rows.filter(r => r._matchStatus === 'matched');
            const exportHeaders = this.headers.filter(h => !h.startsWith('_'));
            const csvLines = [exportHeaders.join(',')];
            for (const row of matchedRows) {
                const values = exportHeaders.map(h => {
                    const val = row[h] || '';
                    if (val.includes(',') || val.includes('"') || val.includes('\n')) {
                        return `"${val.replace(/"/g, '""')}"`;
                    }
                    return val;
                });
                csvLines.push(values.join(','));
            }
            const csvContent = csvLines.join('\n');
            const csvBlob = new Blob([csvContent], { type: 'text/csv' });
            const csvFile = new File([csvBlob], 'import.csv', { type: 'text/csv' });

            const formData = new FormData();
            formData.append('file', csvFile);

            const url = `/api/import-time-reports/import`;

            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Process complete lines (SSE messages end with \n\n)
                const messages = buffer.split('\n\n');
                buffer = messages.pop() || '';

                for (const message of messages) {
                    const lines = message.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                this.handleSSEEvent(data);
                            } catch (e) {
                                console.error('Error parsing SSE:', e, line.substring(0, 100));
                            }
                        }
                    }
                }
            }

            // Process any remaining buffer
            if (buffer.trim()) {
                const lines = buffer.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            this.handleSSEEvent(data);
                        } catch (e) {
                            console.error('Error parsing final SSE:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Import error:', error);
            showNotification('Erreur lors de l\'import', 'error');
        } finally {
            startBtn.disabled = false;
            startBtn.textContent = 'Lancer l\'import';
        }
    },

    handleSSEEvent(data) {
        const progressFill = document.getElementById('import-tr-progress-fill');
        const progressText = document.getElementById('import-tr-progress-text');
        const progressAction = document.getElementById('import-tr-progress-action');
        const actionLog = document.getElementById('import-tr-action-log');
        const resultsSection = document.getElementById('import-tr-results');
        const successCount = document.getElementById('import-tr-success-count');
        const failedCount = document.getElementById('import-tr-failed-count');
        const entriesCount = document.getElementById('import-tr-entries-count');

        switch (data.type) {
            case 'progress':
                progressFill.style.width = `${data.percent}%`;
                progressText.textContent = `${data.percent}% (${data.current}/${data.total})`;
                progressAction.textContent = data.action;
                break;

            case 'action':
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry';
                if (data.message.startsWith('ERROR')) {
                    logEntry.classList.add('error');
                } else if (data.message.includes('cree')) {
                    logEntry.classList.add('success');
                }
                logEntry.textContent = data.message;
                actionLog.appendChild(logEntry);
                actionLog.scrollTop = actionLog.scrollHeight;
                break;

            case 'complete':
                progressFill.style.width = '100%';
                progressText.textContent = '100%';

                // Show results
                resultsSection.classList.remove('hidden');
                successCount.textContent = `Time-reports crees: ${data.success}/${data.total}`;
                failedCount.textContent = data.failed > 0 ? `Echecs: ${data.failed}` : '';
                entriesCount.textContent = `Entrees importees: ${data.total_entries}`;

                if (data.failed === 0) {
                    showNotification(`Import termine ! ${data.total_entries} entrees importees.`, 'success');
                } else {
                    showNotification(`Import termine avec ${data.failed} erreur(s).`, 'warning');
                }
                break;
        }
    }
};

/**
 * Provider Invoices functionality
 */
const providerInvoices = {
    invoicesFile: null,
    purchasesFile: null,
    previewData: null,
    importResults: null,

    init() {
        const invoicesDropzone = document.getElementById('pi-invoices-dropzone');
        const invoicesFileInput = document.getElementById('pi-invoices-file-input');
        const invoicesBrowseBtn = document.getElementById('pi-invoices-browse-btn');
        const invoicesClearBtn = document.getElementById('pi-invoices-clear-btn');

        const purchasesDropzone = document.getElementById('pi-purchases-dropzone');
        const purchasesFileInput = document.getElementById('pi-purchases-file-input');
        const purchasesBrowseBtn = document.getElementById('pi-purchases-browse-btn');
        const purchasesClearBtn = document.getElementById('pi-purchases-clear-btn');

        const previewBtn = document.getElementById('pi-preview-btn');
        const importBtn = document.getElementById('pi-import-btn');
        const downloadCsvBtn = document.getElementById('pi-download-csv-btn');

        const filterStatus = document.getElementById('pi-filter-status');
        const filterSearch = document.getElementById('pi-filter-search');

        if (!invoicesDropzone) return;

        // Invoices file handlers
        this.setupDropzone(invoicesDropzone, invoicesFileInput, invoicesBrowseBtn, (file) => {
            this.invoicesFile = file;
            document.getElementById('pi-invoices-file-name').textContent = file.name;
            document.getElementById('pi-invoices-selected-file').classList.remove('hidden');
            this.updateButtons();
        });

        invoicesClearBtn.addEventListener('click', () => {
            this.invoicesFile = null;
            document.getElementById('pi-invoices-file-input').value = '';
            document.getElementById('pi-invoices-selected-file').classList.add('hidden');
            this.updateButtons();
        });

        // Purchases file handlers
        this.setupDropzone(purchasesDropzone, purchasesFileInput, purchasesBrowseBtn, (file) => {
            this.purchasesFile = file;
            document.getElementById('pi-purchases-file-name').textContent = file.name;
            document.getElementById('pi-purchases-selected-file').classList.remove('hidden');
            this.parsePurchasesCount(file);
        });

        purchasesClearBtn.addEventListener('click', () => {
            this.purchasesFile = null;
            document.getElementById('pi-purchases-file-input').value = '';
            document.getElementById('pi-purchases-selected-file').classList.add('hidden');
            document.getElementById('pi-purchases-count').classList.add('hidden');
        });

        // Action buttons
        previewBtn.addEventListener('click', () => this.preview());
        importBtn.addEventListener('click', () => this.startImport());
        downloadCsvBtn.addEventListener('click', () => this.downloadResultsCSV());

        // Filters
        filterStatus.addEventListener('change', () => this.applyFilters());
        filterSearch.addEventListener('input', () => this.applyFilters());
    },

    setupDropzone(dropzone, fileInput, browseBtn, onFile) {
        browseBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            fileInput.click();
        });

        dropzone.addEventListener('click', () => {
            fileInput.click();
        });

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropzone.classList.add('dragover');
        });

        dropzone.addEventListener('dragleave', () => {
            dropzone.classList.remove('dragover');
        });

        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropzone.classList.remove('dragover');
            if (e.dataTransfer.files.length > 0 && e.dataTransfer.files[0].name.endsWith('.csv')) {
                onFile(e.dataTransfer.files[0]);
            }
        });

        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                onFile(fileInput.files[0]);
            }
        });
    },

    async parsePurchasesCount(file) {
        const content = await file.text();
        const lines = content.split('\n').filter(l => l.trim());
        const count = Math.max(0, lines.length - 1);
        const countEl = document.getElementById('pi-purchases-count');
        countEl.textContent = `${count} achats charges`;
        countEl.classList.remove('hidden');
    },

    updateButtons() {
        const hasInvoices = this.invoicesFile !== null;
        document.getElementById('pi-preview-btn').disabled = !hasInvoices;
        document.getElementById('pi-import-btn').disabled = !this.previewData || this.previewData.rows.length === 0;
    },

    async preview() {
        const previewBtn = document.getElementById('pi-preview-btn');
        previewBtn.disabled = true;
        previewBtn.innerHTML = '<span class="spinner"></span>Chargement...';

        try {
            const formData = new FormData();
            formData.append('invoices_file', this.invoicesFile);
            if (this.purchasesFile) {
                formData.append('purchases_file', this.purchasesFile);
            }

            const response = await fetch('/api/import-provider-invoices/preview', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP error ${response.status}`);
            }

            this.previewData = await response.json();
            this.renderPreview();
            this.updateButtons();

            showNotification(`${this.previewData.rows.length} factures chargees`, 'success');
        } catch (error) {
            console.error('Preview error:', error);
            showNotification('Erreur lors de la previsualisation', 'error');
        } finally {
            previewBtn.disabled = false;
            previewBtn.textContent = 'Previsualiser';
        }
    },

    renderPreview() {
        if (!this.previewData) return;

        const previewSection = document.getElementById('pi-preview-section');
        const tbody = document.getElementById('pi-preview-table').querySelector('tbody');
        const stats = this.previewData.stats;

        // Update stats
        document.getElementById('pi-stat-total').textContent = stats.total;
        document.getElementById('pi-stat-ready').textContent = stats.ready;
        document.getElementById('pi-stat-partial').textContent = stats.partial;
        document.getElementById('pi-stat-error').textContent = stats.error;
        document.getElementById('pi-stat-payment').textContent = stats.with_payment;
        document.getElementById('pi-stat-document').textContent = stats.with_document;

        // Render rows
        this.renderTableRows(this.previewData.rows);

        previewSection.classList.remove('hidden');
    },

    renderTableRows(rows) {
        const tbody = document.getElementById('pi-preview-table').querySelector('tbody');
        tbody.innerHTML = '';

        rows.forEach((row, index) => {
            const tr = document.createElement('tr');
            tr.className = `row-${row.status}`;
            tr.dataset.rowNum = row.row_num;

            // Status icons
            const statusIcon = row.status === 'ready' ? '🟢' : (row.status === 'partial' ? '🟡' : '🔴');

            // File status badge - only show if invoice_file is not empty
            let fileStatusBadge = '';
            if (row.invoice_file && row.invoice_file.trim() !== '') {
                if (row.file_status === 'found') {
                    fileStatusBadge = '<span class="badge badge-success" title="Fichier trouve">✅</span>';
                } else if (row.file_status === 'na') {
                    fileStatusBadge = '<span class="badge badge-neutral" title="Non applicable">➖</span>';
                } else {
                    fileStatusBadge = '<span class="badge badge-error" title="Fichier non trouve">❌</span>';
                }
            }

            const purchaseDisplay = row.purchase_id || '';

            tr.innerHTML = `
                <td>${row.row_num}</td>
                <td>${escapeHtml(row.resource_name)}</td>
                <td>${row.resource_id}</td>
                <td class="editable" data-field="reference" contenteditable="true">${escapeHtml(row.reference)}</td>
                <td class="editable" data-field="invoice_date" contenteditable="true">${row.invoice_date}</td>
                <td class="editable" data-field="start_date" contenteditable="true">${row.start_date}</td>
                <td class="editable" data-field="end_date" contenteditable="true">${row.end_date}</td>
                <td class="editable" data-field="amount_excluding_tax" contenteditable="true">${row.amount_excluding_tax.toFixed(2)}</td>
                <td class="editable" data-field="amount_including_tax" contenteditable="true">${row.amount_including_tax.toFixed(2)}</td>
                <td class="editable ${row.purchase_id ? '' : 'warning'}" data-field="purchase_id" contenteditable="true">${purchaseDisplay}</td>
                <td class="editable" data-field="payment_state" contenteditable="true">${row.payment_state}</td>
                <td>${escapeHtml(row.invoice_file)} ${fileStatusBadge}</td>
                <td>${statusIcon}</td>
            `;

            // Add event listeners for editable cells
            tr.querySelectorAll('.editable').forEach(cell => {
                cell.addEventListener('blur', (e) => this.handleCellEdit(e, row.row_num));
                cell.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        e.target.blur();
                    }
                });
            });

            tbody.appendChild(tr);
        });
    },

    handleCellEdit(event, rowNum) {
        const cell = event.target;
        const field = cell.dataset.field;
        let value = cell.textContent.trim();

        // Find the row in previewData
        const row = this.previewData.rows.find(r => r.row_num === rowNum);
        if (!row) return;

        // Parse value based on field type
        if (field === 'amount_excluding_tax' || field === 'amount_including_tax') {
            value = parseFloat(value.replace(',', '.')) || 0;
            cell.textContent = value.toFixed(2);
        } else if (field === 'payment_state') {
            value = parseInt(value) || 1;
            cell.textContent = value;
        } else if (field === 'purchase_id') {
            // Update warning class based on whether purchase_id is set
            if (value) {
                cell.classList.remove('warning');
            } else {
                cell.classList.add('warning');
            }
        }

        // Update the row data
        row[field] = value;

        // Recalculate invoice_state based on reference
        if (field === 'reference') {
            row.invoice_state = value ? 2 : 1;
        }

        // Recalculate status
        this.recalculateRowStatus(row);

        // Update row class
        const tr = cell.closest('tr');
        tr.className = `row-${row.status}`;

        // Update stats
        this.updateStats();

        // Mark cell as modified
        cell.classList.add('modified');
    },

    recalculateRowStatus(row) {
        // Recalculate errors
        row.errors = [];
        if (!row.resource_id) {
            row.errors.push("resource_id manquant");
        }
        if (!row.start_date || !row.end_date) {
            row.errors.push("dates invalides");
        }

        // Recalculate status
        if (row.errors.length > 0) {
            row.status = "error";
        } else if (!row.purchase_id || row.file_status === "missing") {
            row.status = "partial";
        } else {
            row.status = "ready";
        }
    },

    updateStats() {
        if (!this.previewData) return;

        const rows = this.previewData.rows;
        const stats = {
            total: rows.length,
            ready: rows.filter(r => r.status === 'ready').length,
            partial: rows.filter(r => r.status === 'partial').length,
            error: rows.filter(r => r.status === 'error').length,
            with_payment: rows.filter(r => r.purchase_id).length,
            with_document: rows.filter(r => r.file_status === 'found').length,
        };

        this.previewData.stats = stats;

        document.getElementById('pi-stat-total').textContent = stats.total;
        document.getElementById('pi-stat-ready').textContent = stats.ready;
        document.getElementById('pi-stat-partial').textContent = stats.partial;
        document.getElementById('pi-stat-error').textContent = stats.error;
        document.getElementById('pi-stat-payment').textContent = stats.with_payment;
        document.getElementById('pi-stat-document').textContent = stats.with_document;
    },

    applyFilters() {
        if (!this.previewData) return;

        const statusFilter = document.getElementById('pi-filter-status').value;
        const searchFilter = document.getElementById('pi-filter-search').value.toLowerCase();

        let filteredRows = this.previewData.rows;

        if (statusFilter === 'no_payment') {
            // Filter rows without purchase_id
            filteredRows = filteredRows.filter(r => !r.purchase_id);
        } else if (statusFilter === 'no_document') {
            // Filter rows where file is expected but not found
            filteredRows = filteredRows.filter(r => r.invoice_file && r.file_status === 'missing');
        } else if (statusFilter !== 'all') {
            filteredRows = filteredRows.filter(r => r.status === statusFilter);
        }

        if (searchFilter) {
            filteredRows = filteredRows.filter(r =>
                r.resource_name.toLowerCase().includes(searchFilter)
            );
        }

        this.renderTableRows(filteredRows);
    },

    async startImport() {
        if (!this.previewData || this.previewData.rows.length === 0) {
            showNotification('Veuillez d\'abord previsualiser les donnees', 'error');
            return;
        }

        const importBtn = document.getElementById('pi-import-btn');
        const progressContainer = document.getElementById('pi-progress');
        const progressFill = document.getElementById('pi-progress-fill');
        const progressText = document.getElementById('pi-progress-text');
        const progressAction = document.getElementById('pi-progress-action');
        const actionLog = document.getElementById('pi-action-log');
        const resultsSection = document.getElementById('pi-results');

        importBtn.disabled = true;
        importBtn.innerHTML = '<span class="spinner"></span>Import en cours...';
        progressContainer.classList.remove('hidden');
        resultsSection.classList.add('hidden');
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        progressAction.textContent = '';
        actionLog.innerHTML = '';

        try {
            // Send modified preview data as JSON
            const response = await fetch('/api/import-provider-invoices/import-json', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(this.previewData.rows)
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                const messages = buffer.split('\n\n');
                buffer = messages.pop() || '';

                for (const message of messages) {
                    const lines = message.split('\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                this.handleSSEEvent(data);
                            } catch (e) {
                                console.error('Error parsing SSE:', e);
                            }
                        }
                    }
                }
            }

            // Process remaining buffer
            if (buffer.trim()) {
                const lines = buffer.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.substring(6));
                            this.handleSSEEvent(data);
                        } catch (e) {
                            console.error('Error parsing final SSE:', e);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Import error:', error);
            showNotification('Erreur lors de l\'import', 'error');
        } finally {
            importBtn.disabled = false;
            importBtn.textContent = 'Importer';
        }
    },

    handleSSEEvent(data) {
        const progressFill = document.getElementById('pi-progress-fill');
        const progressText = document.getElementById('pi-progress-text');
        const progressAction = document.getElementById('pi-progress-action');
        const actionLog = document.getElementById('pi-action-log');
        const resultsSection = document.getElementById('pi-results');

        switch (data.type) {
            case 'progress':
                progressFill.style.width = `${data.percent}%`;
                progressText.textContent = `${data.percent}% (${data.current}/${data.total})`;
                progressAction.textContent = data.action;
                break;

            case 'action':
                const logEntry = document.createElement('div');
                logEntry.className = 'log-entry';
                if (data.message.includes('ERROR')) {
                    logEntry.classList.add('error');
                } else if (data.message.includes('WARN')) {
                    logEntry.classList.add('warning');
                } else if (data.message.includes('OK')) {
                    logEntry.classList.add('success');
                }
                logEntry.textContent = data.message;
                actionLog.appendChild(logEntry);
                actionLog.scrollTop = actionLog.scrollHeight;
                break;

            case 'complete':
                progressFill.style.width = '100%';
                progressText.textContent = '100%';

                // Store results for CSV export
                this.importResults = data;

                // Update result stats
                document.getElementById('pi-res-created').textContent = data.stats.invoices_created;
                document.getElementById('pi-res-payments').textContent = data.stats.payments_added;
                document.getElementById('pi-res-documents').textContent = data.stats.documents_attached;
                document.getElementById('pi-res-no-purchase').textContent = data.stats.without_purchase;
                document.getElementById('pi-res-no-document').textContent = data.stats.without_document;
                document.getElementById('pi-res-errors').textContent = data.stats.errors;

                resultsSection.classList.remove('hidden');

                if (data.stats.errors === 0) {
                    showNotification(`Import termine ! ${data.stats.invoices_created} factures creees.`, 'success');
                } else {
                    showNotification(`Import termine avec ${data.stats.errors} erreur(s).`, 'warning');
                }
                break;
        }
    },

    downloadResultsCSV() {
        if (!this.importResults || !this.importResults.results) {
            showNotification('Aucun resultat a exporter', 'error');
            return;
        }

        const headers = [
            'row_num', 'reference', 'resource_name', 'resource_id',
            'invoice_id', 'invoice_status', 'payment_status', 'document_status', 'error'
        ];

        const csvLines = [headers.join(';')];
        for (const r of this.importResults.results) {
            const values = [
                r.row_num,
                r.reference,
                r.resource_name,
                r.resource_id,
                r.invoice_id || '',
                r.invoice_status,
                r.payment_status,
                r.document_status,
                (r.error || '').replace(/;/g, ',')
            ];
            csvLines.push(values.join(';'));
        }

        const csvContent = csvLines.join('\n');
        const today = new Date().toISOString().split('T')[0];
        const filename = `provider_invoices_import_${today}.csv`;

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
    }
};

// Initialize Export Time Reports, Import Time Reports, and Provider Invoices when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    exportTimeReports.init();
    importTimeReports.init();
    providerInvoices.init();
});
