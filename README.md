# Isso Facilita — bot de promoções

MVP para descobrir ofertas de tecnologia na Shopee e no AliExpress, selecionar as
melhores, usar o link de afiliado da plataforma e publicar uma mensagem personalizada.

O projeto já inclui:

- busca agendada nas duas plataformas;
- filtro por palavras de tecnologia e desconto mínimo;
- ranking por desconto;
- link de afiliado retornado/gerado pela API de cada marketplace;
- prevenção de publicação duplicada no mesmo preço;
- curadoria opcional por IA, guiada pela identidade editorial do Isso Facilita;
- copy com símbolos estéticos sem permitir que a IA altere preço, desconto ou link;
- publicação automática no Telegram e, opcionalmente, em grupo comum pelo WhatsApp Web;
- conectores opcionais para WhatsApp Groups API, webhook HTTP ou console;
- modo de demonstração, sem credenciais e sem postagem real;
- API de operação e banco SQLite local.

> Importante: a automação usa APIs de afiliados, não raspagem de páginas. Isso reduz
> quebras e ajuda a respeitar os termos das plataformas. As credenciais nunca devem
> ser colocadas no GitHub.

## Teste rápido

Requer Python 3.11 ou superior.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
isso-facilita run-once
```

O arquivo de exemplo inicia com `demo`, `console` e `DRY_RUN=true`: ele simula ofertas
e apenas mostra as mensagens. Para iniciar o serviço agendado:

```powershell
uvicorn isso_facilita.app:app --reload
```

Acesse `http://localhost:8000` para abrir o painel de compartilhamento. A documentação
da API fica em `http://localhost:8000/docs`. Principais rotas:

- `GET /` — ofertas prontas com botão para compartilhar no WhatsApp;
- `GET /health` — situação do serviço;
- `POST /runs` — executa uma busca imediatamente;
- `GET /publications` — histórico recente.

Se `BOT_API_TOKEN` estiver definido, envie o mesmo valor no cabeçalho `X-API-Token`
nas duas últimas rotas.

## Configuração real

Copie `.env.example` para `.env` e altere:

1. `ENABLED_MARKETPLACES=shopee,aliexpress` (é possível ativar apenas uma);
2. credenciais `SHOPEE_*` e `ALIEXPRESS_*` fornecidas nos portais de afiliados;
3. `PUBLISHER=telegram,whatsapp_web` para publicar nos dois destinos;
4. `DRY_RUN=false` somente depois de validar as mensagens;
5. desconto mínimo, intervalo e limite de posts conforme desejado.

### Curadoria e descrição por IA

A identidade da página fica em `config/brand_identity.json`. Esse arquivo define missão,
público, tom de voz, símbolos, categorias desejadas, rejeições e exemplos de texto. Na
maioria dos casos, ajustar esse perfil e os exemplos é mais simples e econômico do que
treinar um modelo próprio.

O provedor padrão é o Ollama, que executa a IA localmente e não exige chave nem
pagamento por chamada. No computador que ficará ligado:

1. instale o Ollama para Windows em `https://ollama.com/download/windows`;
2. execute `ollama pull qwen3:4b` para baixar o modelo;
3. confirme no `.env` `AI_PROVIDER=ollama` e `OLLAMA_MODEL=qwen3:4b`;
4. defina `AI_CURATION_ENABLED=true`;
5. mantenha `DRY_RUN=true` no primeiro teste e revise as decisões.

O Ollama deve permanecer aberto e atender em `http://127.0.0.1:11434`. A opção
`AI_PROVIDER=openai` continua disponível, mas só deve ser usada com uma
`OPENAI_API_KEY` válida e créditos ativos.

A IA recebe apenas o marketplace e o título oficial. Ela devolve uma decisão de
relevância, uma chamada e uma descrição curtas. O código insere separadamente o título
oficial, preço, desconto e link afiliado, e rejeita qualquer copy que tente acrescentar
números que não existam no título do produto. Se a API de IA falhar, aquele produto não
é publicado e pode ser tentado novamente depois.

### Telegram e WhatsApp

O Telegram é o destino automático principal. Adicione o bot como administrador do
grupo/canal. O `CHAT_ID` pode ser um número (grupos costumam começar com `-100`) ou o
identificador público, como `@meucanal`.

Depois que a oferta for publicada no Telegram, ela aparece em `http://localhost:8000`.
O botão **Compartilhar no WhatsApp** continua disponível como alternativa manual.

### WhatsApp Web não oficial

Para automatizar um grupo comum com o número dedicado, existe um serviço local baseado
em `whatsapp-web.js`. Ele não é uma API oficial da Meta: pode parar após alterações do
WhatsApp e a conta pode sofrer limitação ou bloqueio. Use somente o número separado,
volume baixo e mensagens solicitadas pelos participantes.

Com Node.js 18 ou superior instalado:

```powershell
cd whatsapp-web-bridge
npm install
npm start
```

Abra `http://127.0.0.1:3001`, escaneie o QR Code com o WhatsApp Business do número
dedicado e clique no grupo que receberá as ofertas. A sessão fica salva somente no
computador, em uma pasta ignorada pelo Git.

No `.env`, configure um segredo local em `WHATSAPP_WEB_BRIDGE_TOKEN`, mantenha
`WHATSAPP_WEB_BRIDGE_URL=http://127.0.0.1:3001` e use
`PUBLISHER=telegram,whatsapp_web`. O campo `WHATSAPP_WEB_GROUP_ID` pode ficar vazio,
pois o grupo é escolhido pelo painel. O bot controla cada destino separadamente: se
um canal falhar, o próximo ciclo tenta apenas o canal pendente.

Se `BOT_API_TOKEN` estiver preenchido, abra o painel usando
`http://localhost:8000/?token=SEU_TOKEN`.

### WhatsApp Groups API opcional

O conector usa a API oficial da Meta. São necessários:

- uma conta WhatsApp Business Platform com acesso à Groups API;
- token de acesso permanente em `WHATSAPP_ACCESS_TOKEN`;
- identificador do número empresarial em `WHATSAPP_PHONE_NUMBER_ID`;
- identificador do grupo criado/habilitado pela Groups API em `WHATSAPP_GROUP_ID`;
- a versão da Graph API disponível na conta.

O envio é feito com `recipient_type=group`. Um grupo pessoal existente ou uma
comunidade comum do aplicativo não pode simplesmente receber o bot: o destino precisa
ser reconhecido pela Groups API. Deixe `DRY_RUN=true` até validar todos esses itens.

### Credenciais de marketplace

- Shopee: cadastre/acesse o aplicativo no programa de afiliados e obtenha App ID e
  Secret. O cliente usa o endpoint GraphQL oficial brasileiro.
- AliExpress: obtenha App Key, App Secret e Tracking ID no portal. A documentação
  pública antiga está marcada como descontinuada; por isso o endpoint é configurável.
  Confirme no painel qual endpoint e quais métodos estão liberados para a sua conta.

## Publicação por webhook

O bot envia `POST` com JSON neste formato:

```json
{
  "text": "mensagem pronta",
  "image_url": "https://...",
  "marketplace": "shopee",
  "product_id": "123"
}
```

Isso permite ligar o projeto a Discord, WhatsApp Business, n8n, Make ou outro serviço,
sem alterar o núcleo do bot.

## Docker

Após criar `.env`:

```powershell
docker compose up --build -d
```

## Segurança e operação

- Mantenha `DRY_RUN=true` até revisar as primeiras ofertas.
- Não publique mais do que os grupos aceitam; ajuste `MAX_OFFERS_PER_RUN` e o intervalo.
- Identifique mensagens como link de afiliado. O texto padrão já inclui esse aviso.
- Preços mudam rapidamente; a mensagem informa que o valor deve ser conferido no link.
- O SQLite fica em `data/offers.db`; preserve esse volume para manter a deduplicação.

