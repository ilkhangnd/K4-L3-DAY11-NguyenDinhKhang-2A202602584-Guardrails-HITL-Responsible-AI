const form = document.querySelector('#chat-form');
const input = document.querySelector('#message-input');
const send = document.querySelector('#send-button');
const messages = document.querySelector('#messages');
const status = document.querySelector('#guardrail-status');
const connection = document.querySelector('#connection');
const template = document.querySelector('#message-template');

function addMessage(kind, text, detail = '') {
  const node = template.content.firstElementChild.cloneNode(true);
  // ``kind`` can carry more than one class (for example "assistant typing").
  // DOMTokenList.add accepts individual tokens only; passing the whole string
  // throws and previously stopped the submit handler before fetch() ran.
  node.classList.add(...kind.split(' '));
  node.querySelector('.avatar').textContent = kind === 'user' ? 'YOU' : 'VB';
  node.querySelector('p').textContent = text;
  node.querySelector('small').textContent = detail;
  if (!detail) node.querySelector('small').remove();
  messages.append(node);
  messages.scrollTop = messages.scrollHeight;
  return node;
}

function setGuardrail(layer, text) {
  status.className = 'guardrail-status';
  if (layer === 'input_guardrail' || layer === 'rate_limiter') status.classList.add('blocked');
  if (layer === 'output_guardrail') status.classList.add('redacted');
  status.querySelector('span:last-child').textContent = text;
}

async function checkHealth() {
  try {
    const response = await fetch('/api/health');
    const info = await response.json();
    if (!info.ready) throw new Error('Missing local key');
    connection.className = 'connection';
    connection.textContent = info.mode;
  } catch {
    connection.className = 'connection error';
    connection.textContent = 'Blue model unavailable';
  }
}

async function submitMessage(value) {
  const message = value.trim();
  if (!message) return;
  addMessage('user', message, 'Sent to local Blue pipeline');
  input.value = '';
  input.style.height = 'auto';
  send.disabled = true;
  const typing = addMessage('assistant typing', 'Đang kiểm tra guardrails và tạo phản hồi…');
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message})
    });
    const data = await response.json();
    typing.remove();
    if (!response.ok) throw new Error(data.error || 'Unexpected error');
    const layerText = data.layer
      ? `Layer: ${data.layer}`
      : data.mode === 'fallback'
        ? 'Local fallback — no live LLM response'
        : 'No blocking layer triggered';
    addMessage('assistant', data.response, layerText);
    setGuardrail(data.layer, data.status);
  } catch (error) {
    typing.remove();
    addMessage('assistant', 'Không thể kết nối Blue model lúc này. Vui lòng kiểm tra key và mạng rồi thử lại.', 'Connection error');
    setGuardrail('input_guardrail', 'Model call failed — no response was returned to the browser.');
  } finally {
    send.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', event => { event.preventDefault(); submitMessage(input.value); });
input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submitMessage(input.value); } });
input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 140)}px`; });
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => submitMessage(button.dataset.prompt)));
checkHealth();
