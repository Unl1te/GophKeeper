// --- Configuration ---
const API_BASE = '';  // relative path

// --- DOM refs ---
const loginInput = document.getElementById('loginInput');
const passwordInput = document.getElementById('passwordInput');
const authStatus = document.getElementById('authStatus');
const itemsOutput = document.getElementById('itemsOutput');

const registerBtn = document.getElementById('registerBtn');
const loginBtn = document.getElementById('loginBtn');
const logoutBtn = document.getElementById('logoutBtn');
const createItemBtn = document.getElementById('createItemBtn');
const getItemBtn = document.getElementById('getItemBtn');
const listItemsBtn = document.getElementById('listItemsBtn');
const deleteItemBtn = document.getElementById('deleteItemBtn');

const itemType = document.getElementById('itemType');
const itemContent = document.getElementById('itemContent');
const itemMeta = document.getElementById('itemMeta');
const itemId = document.getElementById('itemId');

// --- Token management ---
function getToken() {
    return localStorage.getItem('gophkeeper_token');
}

function setToken(token) {
    if (token) {
        localStorage.setItem('gophkeeper_token', token);
    } else {
        localStorage.removeItem('gophkeeper_token');
    }
    updateAuthStatus();
}

function updateAuthStatus() {
    const token = getToken();
    if (token) {
        authStatus.innerHTML = 'Logged in. Token: <span class="token">' + token.substring(0, 30) + '...</span>';
    } else {
        authStatus.innerHTML = 'Not logged in. Register or login.';
    }
}

// --- HTTP helpers ---
async function apiRequest(endpoint, method = 'GET', body = null, requireAuth = true) {
    const url = API_BASE + endpoint;
    const headers = { 'Content-Type': 'application/json' };
    if (requireAuth) {
        const token = getToken();
        if (!token) {
            throw new Error('Not authenticated');
        }
        headers['Authorization'] = 'Bearer ' + token;
    }
    const options = {
        method: method,
        headers: headers,
        body: body ? JSON.stringify(body) : null,
    };
    const response = await fetch(url, options);
    if (!response.ok) {
        let detail = await response.text();
        try {
            const json = JSON.parse(detail);
            detail = json.detail || json.message || detail;
        } catch (_) {}
        throw new Error('HTTP ' + response.status + ': ' + detail);
    }
    if (response.status === 204) return null;
    return await response.json();
}

// --- Auth ---
async function register() {
    const login = loginInput.value.trim();
    const password = passwordInput.value;
    if (!login || !password) return alert('Login and password required');
    try {
        const result = await apiRequest('/register', 'POST', { login, password }, false);
        authStatus.innerHTML = 'Registered: ' + (result.message || 'success');
    } catch (e) {
        authStatus.innerHTML = 'Register error: ' + e.message;
    }
}

async function login() {
    const login = loginInput.value.trim();
    const password = passwordInput.value;
    if (!login || !password) return alert('Login and password required');
    try {
        const result = await apiRequest('/login', 'POST', { login, password }, false);
        setToken(result.access_token);
        authStatus.innerHTML = 'Logged in as ' + login;
    } catch (e) {
        authStatus.innerHTML = 'Login error: ' + e.message;
    }
}

function logout() {
    setToken(null);
    authStatus.innerHTML = 'Logged out';
    itemsOutput.innerHTML = 'No items loaded';
}

// --- Items (no encryption, just raw content) ---
async function createItem() {
    const type = itemType.value;
    const content = itemContent.value;
    const metaRaw = itemMeta.value.trim();
    let metadata = {};
    if (metaRaw) {
        try { metadata = JSON.parse(metaRaw); } catch (_) { metadata = { raw: metaRaw }; }
    }

    if (!content) return alert('Content is required');

    const payload = { type, content, metadata };
    try {
        const result = await apiRequest('/items', 'POST', payload);
        itemsOutput.innerHTML = 'Created item: ' + JSON.stringify(result, null, 2);
    } catch (e) {
        itemsOutput.innerHTML = 'Create error: ' + e.message;
    }
}

async function listItems() {
    try {
        const result = await apiRequest('/items');
        if (result.length === 0) {
            itemsOutput.innerHTML = 'No items found.';
            return;
        }
        let html = '<table style="width:100%; border-collapse: collapse; text-align:left;">';
        html += '<tr><th>ID</th><th>Type</th><th>Version</th><th>Updated</th></tr>';
        result.forEach(item => {
            html += '<tr>';
            html += '<td>' + item.id + '</td>';
            html += '<td>' + item.type + '</td>';
            html += '<td>' + item.version + '</td>';
            html += '<td>' + item.updated_at.substring(0,19) + '</td>';
            html += '</tr>';
        });
        html += '</table>';
        html += '<p><em>Use "Get" to view full item (including encrypted content in hex).</em></p>';
        itemsOutput.innerHTML = html;
    } catch (e) {
        itemsOutput.innerHTML = 'List error: ' + e.message;
    }
}

async function getItem() {
    const id = itemId.value.trim();
    if (!id) return alert('Enter item id');

    try {
        const item = await apiRequest('/items/' + id);
        // Show raw item as JSON
        itemsOutput.innerHTML = JSON.stringify(item, null, 2);
    } catch (e) {
        itemsOutput.innerHTML = 'Get error: ' + e.message;
    }
}

async function deleteItem() {
    const id = itemId.value.trim();
    if (!id) return alert('Enter item id');
    if (!confirm('Delete item ' + id + '?')) return;
    try {
        await apiRequest('/items/' + id, 'DELETE');
        itemsOutput.innerHTML = 'Deleted item ' + id;
    } catch (e) {
        itemsOutput.innerHTML = 'Delete error: ' + e.message;
    }
}

// --- Event listeners ---
registerBtn.addEventListener('click', register);
loginBtn.addEventListener('click', login);
logoutBtn.addEventListener('click', logout);
createItemBtn.addEventListener('click', createItem);
listItemsBtn.addEventListener('click', listItems);
getItemBtn.addEventListener('click', getItem);
deleteItemBtn.addEventListener('click', deleteItem);

// --- Init ---
updateAuthStatus();