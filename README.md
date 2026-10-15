# Isso Facilita — bot de promoções

MVP para descobrir ofertas de tecnologia na Shopee e no AliExpress, selecionar as
melhores, usar o link de afiliado da plataforma e publicar uma mensagem personalizada.

O projeto já inclui:

- busca agendada nas duas plataformas;
- filtro por palavras de tecnologia, com produtos promocionais e de preço regular;
- alternância entre ofertas e produtos sem promoção para aumentar a variedade;
- link de afiliado retornado/gerado pela API de cada marketplace;
- prevenção de publicação duplicada no mesmo preço;
- curadoria opcional por IA, guiada pela identidade editorial do Isso Facilita;
- descoberta de figuras e decoração de anime, Sanrio e personagens kawaii;
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
5. desconto mínimo, inclusão de itens sem promoção, intervalo e limite de posts conforme desejado.

### Curadoria e descrição por IA

A identidade da página fica em `config/brand_identity.json`. O aprendizado explícito das
avaliações do proprietário fica em `config/editorial_feedback.json`, separado em produto,
oferta e qualidade da copy. Esses arquivos definem missão, público, preferências,
rejeições e referências; não há fine-tuning do modelo.

O provedor padrão é o Ollama, que executa a IA localmente e não exige chave nem
pagamento por chamada. No computador que ficará ligado:

1. instale o Ollama para Windows em `https://ollama.com/download/windows`;
2. execute `ollama pull qwen3-vl:2b-instruct` para baixar o modelo com visão otimizado para 16 GB de RAM e GTX 1650;
3. confirme no `.env` `AI_PROVIDER=ollama`, `OLLAMA_MODEL=qwen3-vl:2b-instruct` e
   `OLLAMA_USE_PRODUCT_IMAGES=true`;
4. defina `AI_CURATION_ENABLED=true`;
5. mantenha `DRY_RUN=true` no primeiro teste e revise as decisões.

O Ollama deve permanecer aberto e atender em `http://127.0.0.1:11434`. A opção
`AI_PROVIDER=openai` continua disponível, mas só deve ser usada com uma
`OPENAI_API_KEY` válida e créditos ativos.

A IA recebe o marketplace, o título oficial e a imagem principal para identificar o
objeto vendido antes de escrever. Ela devolve uma decisão de relevância, uma chamada e
uma descrição curtas. O código insere separadamente o título
oficial, preço, desconto e link afiliado, e rejeita qualquer copy que tente acrescentar
números que não existam no título do produto. Se a API de IA falhar, aquele produto não
é publicado e pode ser tentado novamente depois.

No modo real, desligar a IA pausa as publicações automáticas. O bot não recorre a uma
copy genérica. Ofertas acima de `MAX_PRODUCT_PRICE_BRL` (R$ 500 por padrão) e categorias
explicitamente incompatíveis são bloqueadas antes de consumir uma avaliação do modelo.

A sequência editorial reserva seis de cada oito posições para setup ou tecnologia,
uma para Action Figures/colecionáveis de anime e Vocaloid e uma para personagens como
Sanrio. A rotação fica salva no banco, evitando que descontos altos produzam várias
publicações do mesmo nicho em seguida. `MAX_AI_EVALUATIONS_PER_RUN` limita quantos itens
o modelo avalia em cada ciclo para controlar o uso de memória e o tempo de processamento.

#### Controle desktop da IA no Windows

O controle desktop altera somente `AI_CURATION_ENABLED` no `.env`. Ao ativar ou
desativar a IA, ele reinicia apenas o processo do bot para aplicar a configuração. No
modo real, desativar a IA mantém o bot online, porém com publicações pausadas;
Ollama e a ponte do WhatsApp permanecem ligados. Nenhuma outra configuração, prompt ou
regra de curadoria é modificada.

Para instalar os atalhos no Desktop e no Menu Iniciar:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_ai_control.ps1
```

Abra **Isso Facilita - Controle da IA** e use **ATIVAR IA** ou **DESATIVAR IA**. O
painel confirma tanto o estado efetivamente carregado pelo bot quanto se ele está
online. A tabela **Avaliações da IA** é atualizada automaticamente e mostra o link,
pontuação e motivo de cada produto aceito ou recusado. Selecione uma linha para ver os
detalhes ou abrir o link afiliado. O histórico começa a ser armazenado localmente em
`data/ai-curation.jsonl` depois desta versão e não é enviado ao Git.

O bloco **Serviços e memória** controla o conjunto completo. **PARAR TUDO** encerra o
bot, a ponte/Chromium dedicado do WhatsApp e o Ollama com o modelo carregado, liberando
a memória sem apagar sessão, banco ou configurações. **INICIAR TUDO** restaura esses
três serviços e respeita o estado atual de `AI_CURATION_ENABLED`.

Para remover apenas os atalhos:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows_ai_control.ps1
```

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
- Se necessário, identifique os links de afiliado na descrição fixa do canal ou grupo.
- Preços mudam rapidamente; confirme o valor no link antes da compra.
- O SQLite fica em `data/offers.db`; preserve esse volume para manter a deduplicação.

