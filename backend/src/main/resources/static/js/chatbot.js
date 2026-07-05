// AI Chatbot for KYC assistance
(function() {
    const chatHTML = `
        <div id="chatbotWidget" class="chatbot-widget" onclick="toggleChat()">
            <span class="chatbot-icon">&#128172;</span>
        </div>
        <div id="chatbotPanel" class="chatbot-panel">
            <div class="chatbot-header">
                <h4>&#129302; KYC Assistant</h4>
                <button onclick="toggleChat()" style="background:none;border:none;color:white;font-size:20px;cursor:pointer">&times;</button>
            </div>
            <div class="chatbot-messages" id="chatMessages">
                <div class="chat-message bot">
                    <div class="message-content">
                        Hello! I'm your KYC assistant. How can I help you today?
                    </div>
                </div>
            </div>
            <div class="chatbot-input">
                <input type="text" id="chatInput" placeholder="Type your question..." onkeypress="if(event.key==='Enter') sendMessage()">
                <button onclick="sendMessage()">&#10148;</button>
            </div>
        </div>
    `;

    const chatCSS = `
        .chatbot-widget {
            position: fixed;
            bottom: 24px;
            right: 24px;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(0, 71, 171, 0.4);
            z-index: 3000;
            transition: var(--transition);
            animation: pulse 2s infinite;
        }
        .chatbot-widget:hover { transform: scale(1.1); }
        .chatbot-panel {
            position: fixed;
            bottom: 100px;
            right: 24px;
            width: 360px;
            max-height: 500px;
            background: var(--white);
            border-radius: var(--radius);
            box-shadow: var(--shadow-lg);
            z-index: 3000;
            display: none;
            flex-direction: column;
            overflow: hidden;
            border: 1px solid var(--gray-200);
            animation: scaleIn 0.3s ease;
        }
        .chatbot-panel.open { display: flex; }
        .chatbot-header {
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            color: white;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .chatbot-header h4 { font-size: 16px; }
        .chatbot-messages {
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            max-height: 350px;
        }
        .chat-message {
            margin-bottom: 12px;
            display: flex;
        }
        .chat-message.bot { justify-content: flex-start; }
        .chat-message.user { justify-content: flex-end; }
        .message-content {
            max-width: 80%;
            padding: 10px 14px;
            border-radius: 12px;
            font-size: 14px;
            line-height: 1.5;
        }
        .chat-message.bot .message-content {
            background: var(--gray-100);
            color: var(--gray-700);
        }
        .chat-message.user .message-content {
            background: var(--primary);
            color: white;
        }
        .chatbot-input {
            display: flex;
            padding: 12px;
            border-top: 1px solid var(--gray-200);
            gap: 8px;
        }
        .chatbot-input input {
            flex: 1;
            padding: 10px 14px;
            border: 2px solid var(--gray-300);
            border-radius: 8px;
            font-size: 14px;
            font-family: var(--font);
        }
        .chatbot-input input:focus { outline: none; border-color: var(--primary); }
        .chatbot-input button {
            padding: 10px 16px;
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
        }
        @media (max-width: 480px) {
            .chatbot-panel { width: calc(100vw - 48px); right: 12px; bottom: 90px; }
        }
    `;

    const style = document.createElement('style');
    style.textContent = chatCSS;
    document.head.appendChild(style);

    const container = document.createElement('div');
    container.innerHTML = chatHTML;
    document.body.appendChild(container);
})();

let isChatOpen = false;

function toggleChat() {
    const panel = document.getElementById('chatbotPanel');
    isChatOpen = !isChatOpen;
    panel.classList.toggle('open');
}

const botResponses = {
    'hello': 'Hello! How can I assist you with your KYC process?',
    'hi': 'Hi there! I\'m your KYC assistant. What do you need help with?',
    'kyc': 'KYC (Know Your Customer) is the process of verifying your identity. You need to:\n1. Register an account\n2. Upload your ID proof (Aadhaar/PAN)\n3. Take a live selfie for face matching\n4. Submit for AI review',
    'document': 'You can upload your Aadhaar or PAN card. Our OCR system will automatically extract your details!',
    'face': 'For face verification, you\'ll need to take a live selfie. Our AI matches it with your ID photo and checks for liveness.',
    'status': 'You can check your KYC status on the KYC Status page under your dashboard.',
    'time': 'The entire KYC process takes about 3 minutes with our AI-powered system!',
    'help': 'I can help you with:\n- KYC process guidance\n- Document requirements\n- Face verification\n- Status tracking\n- Security concerns',
    'security': 'We use Zero Trust architecture with AES-256 encryption, JWT authentication, and real-time fraud detection.',
    'risk': 'Our AI assesses risk based on face match, IP reputation, geolocation, and behavioral analysis.',
    'error': 'If you face any error, please try refreshing the page or contact our support team.',
    'thanks': 'You\'re welcome! Feel free to ask if you need anything else!',
    'bye': 'Goodbye! Have a great day!',
    'default': 'I\'m not sure about that. Please contact our support team or ask about: KYC process, documents, face verification, status, or security.'
};

function sendMessage() {
    const input = document.getElementById('chatInput');
    const messages = document.getElementById('chatMessages');
    const text = input.value.trim();

    if (!text) return;

    // Add user message
    messages.innerHTML += `<div class="chat-message user"><div class="message-content">${escapeHtml(text)}</div></div>`;
    input.value = '';
    messages.scrollTop = messages.scrollHeight;

    // Bot response
    setTimeout(() => {
        const response = getBotResponse(text.toLowerCase());
        messages.innerHTML += `<div class="chat-message bot"><div class="message-content">${response}</div></div>`;
        messages.scrollTop = messages.scrollHeight;
    }, 600);
}

function getBotResponse(input) {
    if (input.includes('hello') || input.includes('hi') || input.includes('hey')) return botResponses.hello;
    if (input.includes('kyc') || input.includes('know your customer')) return botResponses.kyc;
    if (input.includes('document') || input.includes('upload') || input.includes('aadhaar') || input.includes('pan')) return botResponses.document;
    if (input.includes('face') || input.includes('selfie') || input.includes('photo') || input.includes('camera')) return botResponses.face;
    if (input.includes('status') || input.includes('track') || input.includes('progress')) return botResponses.status;
    if (input.includes('time') || input.includes('how long') || input.includes('minute')) return botResponses.time;
    if (input.includes('help') || input.includes('what can')) return botResponses.help;
    if (input.includes('secure') || input.includes('safe') || input.includes('encrypt') || input.includes('protect')) return botResponses.security;
    if (input.includes('risk') || input.includes('score')) return botResponses.risk;
    if (input.includes('error') || input.includes('issue') || input.includes('problem')) return botResponses.error;
    if (input.includes('thank') || input.includes('thanks')) return botResponses.thanks;
    if (input.includes('bye') || input.includes('goodbye')) return botResponses.bye;
    return botResponses.default;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
}
