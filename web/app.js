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

// --- Crypto imports (CDN) ---
import { ChaCha20Poly1305 } from '@stablelib/chacha20poly1305';
import { argon2id } from '@phc/argon2';

// --- Constants ---
const SALT = 'gophkeeper_salt_16bytes';  // must match CLI (as string)

// --- Helper: derive key using Argon2id ---
async function deriveKey(masterPassword) {
    try {
        const hash = await argon2id({
            password: masterPassword,
            salt: SALT,
            parallelism: 4,
            passes: 3,
            memorySize: 65536, // 64 MiB (in KB)
            hashLength: 32,    // 256-bit key
        });
        // hash is a Uint8Array
        return hash;
    } catch (err) {
        console.error('Argon2 error:', err);
        throw new Error('Key derivation failed: ' + err.message);
    }
}

// --- Encryption / Decryption with ChaCha20-Poly1305 ---
function encryptData(plaintext, key) {
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const cipher = new ChaCha20Poly1305(key);
    const plaintextBytes = new TextEncoder().encode(plaintext);
    const ciphertext = cipher.encrypt(nonce, plaintextBytes);
    const result = new Uint8Array(nonce.length + ciphertext.length);
    result.set(nonce, 0);
    result.set(ciphertext, nonce.length);
    return result;
}

function decryptData(combined, key) {
    const nonce = combined.slice(0, 12);
    const ciphertext = combined.slice(12);
    const cipher = new ChaCha20Poly1305(key);
    const plaintextBytes = cipher.decrypt(nonce, ciphertext);
    return new TextDecoder().decode(plaintextBytes);
}

// --- Helper: hex <-> bytes ---
function hexToBytes(hex) {
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) {
        bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return bytes;
}

function bytesToHex(bytes) {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

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

// --- Items ---
async function createItem() {
    const type = itemType.value;
    const content = itemContent.value;
    const metaRaw = itemMeta.value.trim();
    let metadata = {};
    if (metaRaw) {
        try { metadata = JSON.parse(metaRaw); } catch (_) { metadata = { raw: metaRaw }; }
    }

    if (!content) return alert('Content is required');

    const masterPassword = prompt('Master password for encryption:');
    if (!masterPassword) return;

    try {
        const key = await deriveKey(masterPassword);
        const encrypted = encryptData(content, key);
        const hexContent = bytesToHex(encrypted);

        const payload = { type, content: hexContent, metadata };
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
        html += '<p><em>Use "Get" to view full item with decrypted content.</em></p>';
        itemsOutput.innerHTML = html;
    } catch (e) {
        itemsOutput.innerHTML = 'List error: ' + e.message;
    }
}

async function getItem() {
    const id = itemId.value.trim();
    if (!id) return alert('Enter item id');

    const masterPassword = prompt('Master password for decryption:');
    if (!masterPassword) return;

    try {
        const key = await deriveKey(masterPassword);
        const item = await apiRequest('/items/' + id);

        let decryptedText = '';
        try {
            const combined = hexToBytes(item.content);
            decryptedText = decryptData(combined, key);
        } catch (e) {
            decryptedText = '(decryption failed: wrong password or corrupted data)';
        }

        let html = '<div style="border:1px solid #45475a; padding:1em; border-radius:4px; margin-top:0.5em;">';
        html += '<div><strong>ID:</strong> ' + item.id + '</div>';
        html += '<div><strong>Type:</strong> ' + item.type + '</div>';
        html += '<div><strong>Version:</strong> ' + item.version + '</div>';
        html += '<div><strong>Updated:</strong> ' + item.updated_at + '</div>';
        html += '<div><strong>Metadata:</strong> ' + JSON.stringify(item.metadata || {}) + '</div>';
        html += '<div><strong>Decrypted content:</strong> <span style="color:#a6e3a1; word-break:break-all;">' + decryptedText + '</span></div>';
        html += '</div>';
        itemsOutput.innerHTML = html;
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