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
    contracts: {
        requiredFields: ['resource_id ou candidate_id'],
        label: 'Contracts',
        notes: [
            'resource_id OU candidate_id obligatoire (pas les deux)',
            'Les contrats sont tries par start_date pour gerer les renouvellements',
            'Si plusieurs contrats pour une meme ressource sans parent_contract_id, ils sont chaines automatiquement'
        ]
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
        requiredFields: ['resource_id', 'contract_typeOf', 'contract_start_date', 'contract_end_date'],
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
                <td>${r.message || '-'}</td>
            `;
            resultsTbody.appendChild(tr);
        });

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
