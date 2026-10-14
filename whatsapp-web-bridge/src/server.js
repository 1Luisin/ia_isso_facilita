const fs = require("fs");
const path = require("path");

const dotenv = require("dotenv");
const express = require("express");
const QRCode = require("qrcode");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");

const rootDirectory = path.resolve(__dirname, "../..");
dotenv.config({ path: path.join(rootDirectory, ".env") });

const host = process.env.WHATSAPP_WEB_BRIDGE_HOST || "127.0.0.1";
const port = Number(process.env.WHATSAPP_WEB_BRIDGE_PORT || "3001");
const bridgeToken = process.env.WHATSAPP_WEB_BRIDGE_TOKEN || "";
const clientId = process.env.WHATSAPP_WEB_CLIENT_ID || "isso-facilita";
const minimumSendInterval = Number(
  process.env.WHATSAPP_WEB_MIN_SEND_INTERVAL_MS || "5000",
);
const dataDirectory = path.resolve(
  rootDirectory,
  process.env.WHATSAPP_WEB_DATA_PATH || "whatsapp-web-bridge/.data",
);
const stateFile = path.join(dataDirectory, "state.json");

fs.mkdirSync(dataDirectory, { recursive: true });

let status = "starting";
let statusMessage = "Iniciando conexão com o WhatsApp...";
let qrDataUrl = "";
let accountNumber = "";
let selectedGroupId = process.env.WHATSAPP_WEB_GROUP_ID || loadSelectedGroup();
let lastSentAt = 0;
let sendQueue = Promise.resolve();

function loadSelectedGroup() {
  try {
    return JSON.parse(fs.readFileSync(stateFile, "utf8")).selectedGroupId || "";
  } catch (_) {
    return "";
  }
}

function saveSelectedGroup(groupId) {
  fs.writeFileSync(stateFile, JSON.stringify({ selectedGroupId: groupId }, null, 2));
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function requireToken(request, response, next) {
  if (!bridgeToken) {
    return response.status(503).json({ ok: false, error: "Token local não configurado" });
  }
  const supplied = request.get("authorization") || "";
  if (supplied !== `Bearer ${bridgeToken}`) {
    return response.status(401).json({ ok: false, error: "Não autorizado" });
  }
  return next();
}

async function listGroups() {
  if (status !== "ready") return [];
  const chats = await client.getChats();
  return chats
    .filter((chat) => chat.isGroup)
    .map((chat) => ({ id: chat.id._serialized, name: chat.name || "Grupo sem nome" }))
    .sort((left, right) => left.name.localeCompare(right.name, "pt-BR"));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function dashboardHtml(groups) {
  const groupCards = groups.length
    ? groups
        .map(
          (group) => `
            <button class="group ${group.id === selectedGroupId ? "selected" : ""}"
              onclick="selectGroup('${escapeHtml(group.id)}')">
              <strong>${escapeHtml(group.name)}</strong>
              <small>${group.id === selectedGroupId ? "Selecionado" : "Selecionar"}</small>
            </button>`,
        )
        .join("")
    : '<p class="muted">Os grupos aparecerão aqui depois da conexão.</p>';

  const qr = qrDataUrl
    ? `<img class="qr" src="${qrDataUrl}" alt="QR Code para conectar o WhatsApp" />
       <p>Abra o WhatsApp Business no celular → Aparelhos conectados → Conectar aparelho.</p>`
    : "";

  return `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="15" />
  <title>Isso Facilita — WhatsApp</title>
  <style>
    :root { color-scheme: light; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #f7f5f6; color: #2b1f25; }
    main { max-width: 720px; margin: 40px auto; padding: 0 20px; }
    .card { background: white; border-radius: 18px; padding: 28px; box-shadow: 0 8px 30px #3b1b2912; }
    h1 { margin-top: 0; } h2 { margin-top: 32px; font-size: 18px; }
    .status { display: inline-block; border-radius: 999px; padding: 8px 12px; background: #f2d7e2; }
    .status.ready { background: #d7f3e4; color: #17653d; }
    .qr { width: min(320px, 100%); display: block; margin: 24px auto 12px; }
    .groups { display: grid; gap: 10px; }
    .group { border: 1px solid #e5d8de; background: white; border-radius: 12px; padding: 14px 16px;
      text-align: left; cursor: pointer; display: flex; justify-content: space-between; gap: 16px; }
    .group:hover, .group.selected { border-color: #c66a91; background: #fff7fa; }
    small, .muted { color: #7d6871; }
    .warning { margin-top: 24px; font-size: 13px; color: #765c67; }
  </style>
</head>
<body><main><section class="card">
  <h1>WhatsApp do Isso Facilita</h1>
  <p class="status ${status === "ready" ? "ready" : ""}">${escapeHtml(statusMessage)}</p>
  ${accountNumber ? `<p>Número conectado: <strong>${escapeHtml(accountNumber)}</strong></p>` : ""}
  ${qr}
  <h2>Grupo que receberá as ofertas</h2>
  <div class="groups">${groupCards}</div>
  <p class="warning">Esta conexão usa WhatsApp Web por uma biblioteca não oficial. Ela pode parar após mudanças do WhatsApp e há risco de restrição da conta.</p>
</section></main>
<script>
async function selectGroup(groupId) {
  const response = await fetch('/select-group', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({group_id: groupId})
  });
  if (!response.ok) alert('Não foi possível selecionar o grupo.');
  else location.reload();
}
</script></body></html>`;
}

const client = new Client({
  authStrategy: new LocalAuth({ clientId, dataPath: path.join(dataDirectory, "auth") }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  },
});

client.on("qr", async (qr) => {
  status = "qr";
  statusMessage = "Escaneie o QR Code para conectar o número dedicado";
  qrDataUrl = await QRCode.toDataURL(qr, { width: 360, margin: 1 });
});

client.on("authenticated", () => {
  status = "authenticated";
  statusMessage = "QR Code confirmado. Preparando as conversas...";
  qrDataUrl = "";
});

client.on("ready", () => {
  status = "ready";
  statusMessage = "WhatsApp conectado e pronto para publicar";
  accountNumber = client.info?.wid?.user || "";
  qrDataUrl = "";
  console.log("WhatsApp conectado e pronto.");
});

client.on("auth_failure", () => {
  status = "auth_failure";
  statusMessage = "Falha na autenticação. Recarregue para gerar um novo QR Code.";
  qrDataUrl = "";
  console.error("Falha na autenticação do WhatsApp.");
});

client.on("disconnected", (reason) => {
  status = "disconnected";
  statusMessage = `WhatsApp desconectado: ${reason}`;
  qrDataUrl = "";
  console.warn("WhatsApp desconectado.");
});

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/", async (_, response) => {
  try {
    response.type("html").send(dashboardHtml(await listGroups()));
  } catch (_) {
    response.type("html").send(dashboardHtml([]));
  }
});

app.get("/health", (_, response) => {
  response.json({ ok: true, status, ready: status === "ready", group_selected: !!selectedGroupId });
});

app.get("/groups", requireToken, async (_, response) => {
  if (status !== "ready") return response.status(503).json({ ok: false, error: "WhatsApp ainda não está conectado" });
  return response.json({ ok: true, groups: await listGroups(), selected_group_id: selectedGroupId });
});

app.post("/select-group", async (request, response) => {
  if (status !== "ready") return response.status(503).json({ ok: false, error: "WhatsApp ainda não está conectado" });
  const groupId = String(request.body?.group_id || "");
  const groups = await listGroups();
  if (!groups.some((group) => group.id === groupId)) {
    return response.status(400).json({ ok: false, error: "Grupo inválido" });
  }
  selectedGroupId = groupId;
  saveSelectedGroup(groupId);
  return response.json({ ok: true });
});

app.post("/send", requireToken, (request, response) => {
  const task = async () => {
    if (status !== "ready") throw Object.assign(new Error("WhatsApp ainda não está conectado"), { statusCode: 503 });
    const text = String(request.body?.text || "").trim();
    const groupId = String(request.body?.group_id || selectedGroupId || "");
    const imageUrl = String(request.body?.image_url || "").trim();
    if (!text) throw Object.assign(new Error("Mensagem vazia"), { statusCode: 400 });
    if (!groupId.endsWith("@g.us")) throw Object.assign(new Error("Selecione um grupo no painel local"), { statusCode: 400 });

    const chat = await client.getChatById(groupId);
    if (!chat?.isGroup) throw Object.assign(new Error("O destino selecionado não é um grupo"), { statusCode: 400 });

    const elapsed = Date.now() - lastSentAt;
    if (elapsed < minimumSendInterval) await wait(minimumSendInterval - elapsed);

    let message;
    let mediaAttached = false;
    if (imageUrl) {
      try {
        const media = await MessageMedia.fromUrl(imageUrl, { unsafeMime: true });
        message = await chat.sendMessage(media, { caption: text });
        mediaAttached = true;
      } catch (error) {
        console.error("Não foi possível anexar a imagem do produto.", error);
        throw Object.assign(
          new Error("Não foi possível anexar a imagem do produto"),
          { statusCode: 502 },
        );
      }
    } else {
      message = await chat.sendMessage(text, { linkPreview: false });
    }
    lastSentAt = Date.now();
    return { message, mediaAttached };
  };

  sendQueue = sendQueue.then(task, task);
  sendQueue
    .then(({ message, mediaAttached }) => response.json({
      ok: true,
      message_id: message.id?._serialized || "",
      media_attached: mediaAttached,
    }))
    .catch((error) => {
      console.error("Falha ao enviar mensagem ao grupo.");
      response.status(error.statusCode || 500).json({ ok: false, error: error.message || "Falha no envio" });
    });
});

const server = app.listen(port, host, () => {
  console.log(`Painel do WhatsApp disponível em http://${host}:${port}`);
});

client.initialize().catch(() => {
  status = "error";
  statusMessage = "Não foi possível iniciar o WhatsApp Web";
  console.error("Não foi possível iniciar o WhatsApp Web.");
});

async function shutdown() {
  server.close();
  try {
    await client.destroy();
  } finally {
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
