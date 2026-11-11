# Macro Dashboard

🇺🇸 [English](README.md) · 🇧🇷 **Português**

**Um dashboard macroeconômico ao vivo com indicadores dos EUA e do Brasil — e comentário gerado por IA no estilo de um estrategista macro de sell-side.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Visit%20Dashboard-blue?style=flat-square)](https://your-deployment-url-here)
![Python](https://img.shields.io/badge/Python-3.11+-informational?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?style=flat-square)
![Plotly](https://img.shields.io/badge/Plotly-5.x-3F4F75?style=flat-square)

---

## O que faz

- **Busca dados macro ao vivo** em três APIs públicas — Federal Reserve (FRED), Bureau of Labor Statistics (BLS) e Banco Central do Brasil (BCB) — e junta tudo em uma única base consolidada, sob demanda.
- **Mostra cinco gráficos interativos**: Fed Funds vs. desemprego, inflação ao consumidor dos EUA (CPI, 12 meses), nível e variação mensal do Nonfarm Payrolls, emprego privado por setor (bens vs. serviços, área empilhada) e Selic vs. IPCA.
- **Exibe sete indicadores em tempo real** — Fed Funds, desemprego, CPI, payrolls total e privado (EUA), Selic e IPCA — cada um com a variação mensal em cores, indicando se a leitura melhorou ou piorou em relação ao período anterior.
- **Gera comentário estruturado por IA** via API da Anthropic (Claude): uma nota a clientes em três seções, cobrindo o cenário macro americano, o ciclo de política monetária brasileiro e as implicações de posicionamento entre classes de ativos.

---

## Por que isso importa para gestores de portfólio

Os indicadores acompanhados aqui são exatamente os dados que orientam as decisões de alocação em renda fixa e ações nas gestoras brasileiras que atuam nos mercados doméstico e internacional:

**Fed Funds e CPI (EUA)** definem o juro real no maior mercado de títulos do mundo. Quando o juro real americano está muito positivo, ele atrai capital para fora dos emergentes e pressiona o real — algo diretamente relevante para qualquer fundo com exposição internacional.

**Payrolls e desemprego (EUA)** são o segundo mandato do Fed. Um mercado de trabalho que não desacelera obriga o FOMC a manter os juros altos por mais tempo, reduzindo o apetite a risco global e apertando as condições financeiras dos emergentes.

**Selic e IPCA (Brasil)** definem a taxa livre de risco doméstica e o juro real que a renda fixa brasileira oferece em relação aos EUA. O diferencial entre Selic e Fed Funds — e a direção em que ele se move — é um dado central para o posicionamento em duration em títulos locais e para operações de carry com o real.

Para um gestor de uma casa brasileira, ler os sete números ao mesmo tempo — e entender como eles interagem — é o ponto de partida de qualquer discussão de alocação.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11, Flask |
| Pipeline de dados | Pandas, Requests |
| Visualização | Plotly (graph_objects, make_subplots) |
| Comentário por IA | Anthropic Python SDK (Claude claude-sonnet-4-6) |
| Frontend | JavaScript puro, HTML/CSS (sem framework) |
| Servidor | Gunicorn (produção), servidor de desenvolvimento do Flask (local) |
| Ambiente | python-dotenv |

---

## Fontes de dados

| Fonte | O que fornece | API |
|---|---|---|
| [FRED](https://fred.stlouisfed.org) — Federal Reserve Bank of St. Louis | Fed Funds (`FEDFUNDS`), taxa de desemprego (`UNRATE`), CPI (`CPIAUCSL`) | [FRED API](https://fred.stlouisfed.org/docs/api/fred/) |
| [BLS](https://www.bls.gov) — Bureau of Labor Statistics | Payrolls total e do setor privado, emprego na produção de bens e em serviços privados | [BLS Public Data API](https://www.bls.gov/developers/) |
| [BCB](https://www.bcb.gov.br) — Banco Central do Brasil | Meta da Selic (série 432), IPCA acumulado em 12 meses (série 13522) | [API SGS do BCB](https://www.bcb.gov.br/content/config/docs/APISeries_en.pdf) |

As três APIs são gratuitas e não exigem chave de autenticação para as séries usadas aqui (uma chave registrada no BLS aumenta o limite de requisições, mas é opcional).

---

## Como funciona o comentário por IA

Ao clicar em **Generate Commentary**, o dashboard:

1. Lê a linha mais recente da base consolidada e monta um bloco de dados enxuto — Fed Funds, desemprego, CPI em 12 meses, variação mensal do payrolls, Selic e IPCA em 12 meses.
2. Envia esse bloco ao Claude pela API da Anthropic, com um prompt de sistema cuidadosamente construído que pede três seções distintas:
   - **Estados Unidos** — 4 a 5 frases sobre o nível do juro real, a trajetória da inflação e o que ela implica para o calendário de cortes, o ritmo do mercado de trabalho e os riscos de curto prazo.
   - **Brasil** — 4 a 5 frases sobre a Selic real, o ritmo de convergência do IPCA, as restrições fiscais ao ciclo de cortes e uma comparação direta entre os ciclos do BCB e do Fed, com a implicação para o real.
   - **Implicações para gestão de ativos** — exatamente três frases, uma por classe de ativo: uma visão de duration para renda fixa, cíclicas vs. defensivas para ações e uma postura risk-on/risk-off para emergentes.
3. Guarda o resultado em cache por 12 horas (configurável) para evitar chamadas repetidas à API a cada carregamento da página. O cache é invalidado automaticamente quando os dados são atualizados.

O prompt usa `cache_control: ephemeral` no prompt de sistema, que o mantém no cache de prompts da Anthropic e reduz latência e custo em chamadas repetidas com as mesmas instruções.

---

## Como rodar localmente

**Pré-requisitos:** Python 3.11+, uma chave da API do FRED (gratuita) e uma chave da API da Anthropic (para o comentário por IA).

```bash
# 1. Clone o repositório
git clone https://github.com/joaoalbuquerquef/macro-dashboard.git
cd macro-dashboard

# 2. Crie e ative um ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o .env e preencha:
#   FRED_API_KEY=sua_chave_fred
#   ANTHROPIC_API_KEY=sua_chave_anthropic
#   BLS_API_KEY=sua_chave_bls   # opcional — o nível público funciona sem ela

# 5. Baixe os dados e monte a base consolidada
python explore_fred.py
python explore_bls.py
python explore_bcb.py           # opcional — o dashboard continua funcionando se o BCB estiver fora do ar
python build_master.py

# 6. Suba o servidor de desenvolvimento do Flask
python app.py
```

Abra [http://localhost:5000](http://localhost:5000). Use o botão **Refresh Data** no cabeçalho para rodar o pipeline completo em segundo plano; a página recarrega sozinha ao terminar.

---

## Estrutura do projeto

```
macro-dashboard/
├── app.py              # App Flask — rotas, atualização assíncrona, comentário por IA
├── charts.py           # Cinco funções de gráficos em Plotly
├── build_master.py     # Junta FRED + BLS + BCB em data/master.csv
├── explore_fred.py     # Cliente da API do FRED → data/fred_raw.csv
├── explore_bls.py      # Cliente da API do BLS → data/bls_raw.csv
├── explore_bcb.py      # Cliente da API SGS do BCB → data/bcb_raw.csv
├── templates/
│   └── index.html      # Dashboard de página única (Jinja2 + JavaScript puro)
├── data/               # CSVs gerados automaticamente (fora do git)
├── requirements.txt
└── .env.example
```

---

## Autor

Desenvolvido como parte de um portfólio de finanças quantitativas durante os estudos na Sciences Po Paris, na preparação para uma carreira em gestão de ativos no Brasil.

O projeto é propositalmente completo de ponta a ponta — pipeline de dados, visualização e integração com IA — para refletir o tipo de trabalho que fica na interseção entre pesquisa macro, tecnologia e comunicação com clientes em uma gestora moderna.
