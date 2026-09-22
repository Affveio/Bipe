const API_URL = (window.location.origin && window.location.origin.startsWith('http')) ? window.location.origin : 'http://127.0.0.1:5055';
let rawHistory = [];
let todasPlataformas = {};
let todosMotoristas = [];
let todasCidades = [];

function normalizarMotoristas(data) {
    if (!data) return [];
    if (Array.isArray(data)) {
        return data.map(item => ({
            cidade: (item.cidade || '').trim(),
            motorista: (item.motorista || '').trim()
        })).filter(item => item.cidade && item.motorista);
    }
    if (typeof data === 'object') {
        const lista = [];
        for (const [cidade, mot] of Object.entries(data)) {
            if (Array.isArray(mot)) {
                mot.forEach(m => {
                    if (cidade && m) lista.push({ cidade: cidade.trim(), motorista: String(m).trim() });
                });
            } else if (mot) {
                lista.push({ cidade: cidade.trim(), motorista: String(mot).trim() });
            }
        }
        return lista;
    }
    return [];
}

// Elementos do DOM - Filtros
const filterPlatform = document.getElementById('filter-platform');
const filterStatus = document.getElementById('filter-status');
const filterDeliveryStatus = document.getElementById('filter-delivery-status');
const searchInput = document.getElementById('search-input');
const motoristaPlataformaSelect = document.getElementById('motorista-plataforma-select');

// Filtro de Período Geral
const periodStart = document.getElementById('period-start');
const periodEnd = document.getElementById('period-end');
const btnSearchPeriod = document.getElementById('btn-search-period');

// Elementos do DOM - Ações / Tabela
const auditTableBody = document.getElementById('audit-table-body');
const btnClearHistory = document.getElementById('btn-clear-history');

// Elementos de Importação Excel / Reconciliação
const importFile = document.getElementById('import-file');
const fileDropZone = document.getElementById('file-drop-zone');
const btnProcessImport = document.getElementById('btn-process-import');
const importStatusText = document.getElementById('import-status-text');
const importPlatform = document.getElementById('import-platform');
const driverPerformanceBody = document.getElementById('driver-performance-body');
const driverSummaryBody = document.getElementById('driver-summary-body');

// Atalhos de Importação Local
const btnImportLocalAnjun = document.getElementById('btn-import-local-anjun');
const btnImportLocalImile = document.getElementById('btn-import-local-imile');
const btnImportLocalDelivered = document.getElementById('btn-import-local-delivered');

// Grid de Cartões de Motoristas
const driverCardsContainer = document.getElementById('driver-cards-container');

// Elementos de Indicadores KPIs
const kpiTotalTriados = document.getElementById('kpi-total-triados');
const kpiTotalEntregues = document.getElementById('kpi-total-entregues');
const kpiTotalEmRota = document.getElementById('kpi-total-em-rota');
const kpiTotalProblemas = document.getElementById('kpi-total-problemas');
const kpiTotalPendentes = document.getElementById('kpi-total-pendentes');
const kpiTaxaAproveitamento = document.getElementById('kpi-taxa-aproveitamento');

// Elementos do Modal de Configurações
const settingsModal = document.getElementById('settings-modal');
const btnSettings = document.getElementById('btn-settings');
const btnCloseModal = document.getElementById('btn-close-modal');

// Elementos do Modal de Conciliação
const reconcileModal = document.getElementById('reconcile-modal');
const btnToggleReconciliar = document.getElementById('btn-toggle-reconciliar');
const btnCloseReconcileModal = document.getElementById('btn-close-reconcile-modal');
const tabLinks = document.querySelectorAll('.tab-link');
const tabContents = document.querySelectorAll('.tab-content');

// Elementos da Aba de Cidades
const cidadesListBody = document.getElementById('cidades-list-body');
const formCidade = document.getElementById('form-cidade');
const cidNome = document.getElementById('cid-nome');

// Elementos da Aba de Motoristas
const motoristasListBody = document.getElementById('motoristas-list-body');
const formMotorista = document.getElementById('form-motorista');
const motCidadeSelect = document.getElementById('mot-cidade-select');
const motNome = document.getElementById('mot-nome');

// Elementos da Aba de Plataformas
const platformsButtonsContainer = document.getElementById('platforms-buttons-container');
const btnNewPlatform = document.getElementById('btn-new-platform');
const formPlataforma = document.getElementById('form-plataforma');
const platFormTitle = document.getElementById('platform-form-title');
const platId = document.getElementById('plat-id');
const platIdInput = document.getElementById('plat-id-input');
const platNome = document.getElementById('plat-nome');
const platRecebimentoUrl = document.getElementById('plat-recebimento-url');
const platRecebimentoInputXpath = document.getElementById('plat-recebimento-input-xpath');
const platRecebimentoDadosXpath = document.getElementById('plat-recebimento-dados-xpath');
const platAtribuicaoUrl = document.getElementById('plat-atribuicao-url');
const platAtribuicaoMotoristaXpath = document.getElementById('plat-atribuicao-motorista-xpath');
const platAtribuicaoBipXpath = document.getElementById('plat-atribuicao-bip-xpath');
const platLoginUser = document.getElementById('plat-login-user');
const platLoginPass = document.getElementById('plat-login-pass');
const btnDeletePlatform = document.getElementById('btn-delete-platform');

// Instâncias dos gráficos
let chartCidadesInst = null;
let chartPlataformasInst = null;
let chartMotoristasInst = null;

// Configuração padrão de fontes e cores para o Chart.js (Dark Mode)
Chart.defaults.color = '#94a3b8';
Chart.defaults.font.family = "'Outfit', sans-serif";
Chart.defaults.font.size = 11;

// 1. INICIALIZAÇÃO E CARREGAMENTO DE DADOS
async function inicializarDashboard() {
    try {
        // 1. Registrar todos os Listeners de Eventos primeiro (para garantir que a UI responda mesmo se o servidor estiver offline)
        if (filterPlatform) filterPlatform.addEventListener('change', processarFiltros);
        if (filterStatus) filterStatus.addEventListener('change', processarFiltros);
        if (filterDeliveryStatus) filterDeliveryStatus.addEventListener('change', processarFiltros);
        if (searchInput) searchInput.addEventListener('input', processarFiltros);
        if (btnClearHistory) btnClearHistory.addEventListener('click', limparHistoricoServidor);
        if (motoristaPlataformaSelect) {
            motoristaPlataformaSelect.addEventListener('change', atualizarMotoristasDaPlataformaSelecionada);
        }

        // Lógica de drag & drop e upload da planilha
        if (fileDropZone && importFile) {
            fileDropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                fileDropZone.classList.add('dragover');
            });

            fileDropZone.addEventListener('dragleave', () => {
                fileDropZone.classList.remove('dragover');
            });

            fileDropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                fileDropZone.classList.remove('dragover');
                if (e.dataTransfer.files.length > 0) {
                    importFile.files = e.dataTransfer.files;
                    atualizarVisualArquivoSelecionado();
                }
            });

            importFile.addEventListener('change', () => {
                atualizarVisualArquivoSelecionado();
            });
        }

        if (btnProcessImport) {
            btnProcessImport.addEventListener('click', processarPlanilhaExcel);
        }

        if (btnImportLocalAnjun) {
            btnImportLocalAnjun.addEventListener('click', () => processarImportacaoLocal("Anjun.xlsx"));
        }

        if (btnImportLocalImile) {
            btnImportLocalImile.addEventListener('click', () => processarImportacaoLocal("Imile.xlsx"));
        }

        if (btnImportLocalDelivered) {
            btnImportLocalDelivered.addEventListener('click', () => processarImportacaoLocal("Delivered.xlsx"));
        }

        if (btnSearchPeriod) {
            btnSearchPeriod.addEventListener('click', async () => {
                await atualizarDados();
            });
        }

        // Inicializa o período com os últimos 7 dias por padrão para garantir exibição de dados
        const hoje = new Date();
        const seteDiasAtras = new Date(hoje.getTime() - 7 * 24 * 60 * 60 * 1000);
        const hojeStr = hoje.toISOString().split('T')[0];
        const seteDiasAtrasStr = seteDiasAtras.toISOString().split('T')[0];
        if (periodStart && !periodStart.value) periodStart.value = seteDiasAtrasStr;
        if (periodEnd && !periodEnd.value) periodEnd.value = hojeStr;

        if (btnSettings) {
            btnSettings.addEventListener('click', () => {
                settingsModal.classList.add('active');
            });
        }

        if (btnCloseModal) {
            btnCloseModal.addEventListener('click', () => {
                settingsModal.classList.remove('active');
            });
        }

        if (btnToggleReconciliar) {
            btnToggleReconciliar.addEventListener('click', () => {
                reconcileModal.classList.add('active');
            });
        }

        if (btnCloseReconcileModal) {
            btnCloseReconcileModal.addEventListener('click', () => {
                reconcileModal.classList.remove('active');
            });
        }

        // Alternância de Abas
        tabLinks.forEach(link => {
            link.addEventListener('click', () => {
                tabLinks.forEach(l => l.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));
                
                link.classList.add('active');
                const tabId = link.getAttribute('data-tab');
                const tabEl = document.getElementById(tabId);
                if (tabEl) tabEl.classList.add('active');
            });
        });

        // Listeners dos formulários do modal
        if (formCidade) formCidade.addEventListener('submit', salvarNovaCidade);
        if (formMotorista) formMotorista.addEventListener('submit', salvarMapeamentoMotorista);
        if (formPlataforma) formPlataforma.addEventListener('submit', salvarConfigPlataforma);
        if (btnNewPlatform) btnNewPlatform.addEventListener('click', limparFormularioPlataforma);
        if (btnDeletePlatform) btnDeletePlatform.addEventListener('click', deletarPlataformaServidor);

        // 2. Carrega configurações do servidor
        const resConfig = await fetch(`${API_URL}/configuracoes`);
        if (resConfig.ok) {
            const data = await resConfig.json();
            todasPlataformas = data.plataformas || {};
            todasCidades = (data.cidades || []).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            
            // Popula filtros e listas do modal
            popularFiltroPlataformas();
            renderizarListaCidades();
            popularMotoristaPlataformaDropdown();
            await atualizarMotoristasDaPlataformaSelecionada();
            renderizarBotoesPlataformas();
        }

        // 3. Carrega o histórico
        await atualizarDados();

    } catch (err) {
        console.error("Falha ao inicializar o dashboard", err);
        if (auditTableBody) {
            auditTableBody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: #ef4444; padding: 20px;">Erro ao conectar com o servidor local. Verifique se o app.py está rodando.</td></tr>`;
        }
    }
}

// 2. BUSCAR DADOS DO BACKEND
async function atualizarDados() {
    const startVal = periodStart ? periodStart.value : "";
    const endVal = periodEnd ? periodEnd.value : "";
    
    let url = `${API_URL}/historico`;
    if (startVal && endVal) {
        url += `?data_inicio=${startVal}&data_fim=${endVal}`;
    }
    
    const res = await fetch(url);
    if (!res.ok) throw new Error("Erro ao carregar histórico");
    rawHistory = await res.json();
    
    processarFiltros();
}

// Recarrega as configurações do backend e atualiza tabelas/listas
async function recarregarConfiguracoes() {
    try {
        const resConfig = await fetch(`${API_URL}/configuracoes`);
        if (resConfig.ok) {
            const data = await resConfig.json();
            todasPlataformas = data.plataformas || {};
            todasCidades = (data.cidades || []).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            
            popularFiltroPlataformas();
            renderizarListaCidades();
            popularMotoristaPlataformaDropdown();
            await atualizarMotoristasDaPlataformaSelecionada();
            renderizarBotoesPlataformas();
            
            processarFiltros();
        }
    } catch (e) {
        console.error("Erro ao recarregar configurações", e);
    }
}

// Popula o dropdown da aba de motoristas
function popularMotoristaPlataformaDropdown() {
    if (!motoristaPlataformaSelect) return;
    const ids = Object.keys(todasPlataformas);
    const valorAtual = motoristaPlataformaSelect.value;
    
    const options = ids.map(id => `<option value="${id}">${todasPlataformas[id].nome}</option>`).join('');
    motoristaPlataformaSelect.innerHTML = options;
    
    if (valorAtual && ids.includes(valorAtual)) {
        motoristaPlataformaSelect.value = valorAtual;
    } else if (ids.length > 0) {
        motoristaPlataformaSelect.value = ids[0];
    }
}

// Carrega os motoristas cadastrados para a plataforma selecionada
async function atualizarMotoristasDaPlataformaSelecionada() {
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "";
    if (!platId) return;
    
    try {
        const res = await fetch(`${API_URL}/configuracoes?plataforma=${platId}`);
        if (res.ok) {
            const data = await res.json();
            todosMotoristas = normalizarMotoristas(data.motoristas);
            renderizarListaMotoristas();
        }
    } catch (err) {
        console.error("Erro ao carregar motoristas da plataforma", err);
    }
}

// 3. POPULAR DROPDOWN DE FILTRO DE PLATAFORMA
function popularFiltroPlataformas() {
    const ids = Object.keys(todasPlataformas);
    const options = ids.map(id => `<option value="${id}">${todasPlataformas[id].nome}</option>`).join('');
    filterPlatform.innerHTML = '<option value="">Todas</option>' + options;
}

// 4. PROCESSAR FILTROS EM TEMPO REAL E ATUALIZAR VIEW
function processarFiltros() {
    const platSel = filterPlatform.value;
    const statusSel = filterStatus.value;
    const delStatusSel = filterDeliveryStatus ? filterDeliveryStatus.value : "";
    const query = searchInput.value.toLowerCase().trim();

    // Filtragem
    const dadosFiltrados = rawHistory.filter(item => {
        // Filtro por plataforma
        if (platSel && item.plataforma !== platSel) return false;
        
        // Filtro por status de triagem
        if (statusSel) {
            const isOk = item.status === 'OK';
            if (statusSel === 'ok' && !isOk) return false;
            if (statusSel === 'falha' && isOk) return false;
        }

        // Filtro por status de entrega (conciliação Excel)
        if (delStatusSel) {
            const hasStatus = item.status_entrega ? item.status_entrega.trim().toUpperCase() : "";
            if (delStatusSel === 'PENDENTE' && hasStatus !== "") return false;
            if (delStatusSel !== 'PENDENTE' && hasStatus !== delStatusSel) return false;
        }

        // Filtro por termo de busca (código, motorista, cidade, recebedor, telefone ou email)
        if (query) {
            const codMatch = item.codigo ? item.codigo.toLowerCase().includes(query) : false;
            const motMatch = item.motorista ? item.motorista.toLowerCase().includes(query) : false;
            const cidMatch = item.cidade ? item.cidade.toLowerCase().includes(query) : false;
            const recMatch = item.recebedor ? item.recebedor.toLowerCase().includes(query) : false;
            const telMatch = item.telefone ? item.telefone.toLowerCase().includes(query) : false;
            const emailMatch = item.email ? item.email.toLowerCase().includes(query) : false;
            const statusEntMatch = item.status_entrega ? item.status_entrega.toLowerCase().includes(query) : false;
            const motEntMatch = item.motorista_entrega ? item.motorista_entrega.toLowerCase().includes(query) : false;
            if (!codMatch && !motMatch && !cidMatch && !recMatch && !telMatch && !emailMatch && !statusEntMatch && !motEntMatch) return false;
        }

        return true;
    });

    // Atualiza Tabela
    atualizarTabela(dadosFiltrados);

    // Calcula Desempenho dos Motoristas
    calcularDesempenhoMotoristas(dadosFiltrados);

    // Atualiza Gráficos
    renderizarGraficoCidades(dadosFiltrados);
    renderizarGraficoPlataformas(dadosFiltrados);
    renderizarGraficoMotoristas(dadosFiltrados);
}

// 5. RENDERIZAR TABELA DETALHADA
function atualizarTabela(dados) {
    if (dados.length === 0) {
        auditTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: #94a3b8; padding: 30px;">Nenhum registro encontrado com os filtros selecionados.</td></tr>`;
        return;
    }

    auditTableBody.innerHTML = dados.slice().reverse().map(item => {
        const dataHora = new Date(item.timestamp).toLocaleString('pt-BR');
        const badgeClass = item.status === 'OK' ? 'ok' : 'fail';
        const platNome = todasPlataformas[item.plataforma]?.nome || item.plataforma.toUpperCase();
        
        // Status da entrega (planilha)
        let deliveryBadge = '<span class="status-badge pendente">PENDENTE</span>';
        const sEnt = item.status_entrega ? item.status_entrega.toUpperCase().trim() : "";
        if (sEnt === "ENTREGUE") {
            deliveryBadge = '<span class="status-badge entregue">ENTREGUE</span>';
        } else if (sEnt === "EM ROTA") {
            deliveryBadge = '<span class="status-badge em-rota">EM ROTA</span>';
        } else if (sEnt === "PROBLEMA") {
            deliveryBadge = '<span class="status-badge problema">PROBLEMA</span>';
        } else if (sEnt !== "") {
            deliveryBadge = `<span class="status-badge pendente">${sEnt}</span>`;
        }

        // Calcula e exibe dias de atraso se o pacote não estiver Entregue e tiver >= 3 dias
        let delayWarning = "";
        if (sEnt !== "ENTREGUE" && item.tempo_atraso && item.tempo_atraso >= 3.0) {
            const diasAtraso = Math.floor(item.tempo_atraso);
            delayWarning = `<span class="status-badge problema" style="margin-left: 5px; background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #f87171; font-weight: 700; font-size: 0.75rem;" title="Pacote com atraso no site há ${item.tempo_atraso.toFixed(1)} dias!">⚠️ ${diasAtraso}d atraso</span>`;
        }

        // Valida se o motorista do site é o mesmo do local
        let motoristaPlanilhaTd = '<td style="color: #64748b">---</td>';
        if (item.motorista_entrega) {
            const mLocalClean = item.motorista.trim().toLowerCase();
            const mPlanilhaClean = item.motorista_entrega.trim().toLowerCase();
            if (mLocalClean === mPlanilhaClean || mPlanilhaClean.includes(mLocalClean) || mLocalClean.includes(mPlanilhaClean)) {
                motoristaPlanilhaTd = `<td>${item.motorista_entrega}</td>`;
            } else {
                motoristaPlanilhaTd = `<td style="color: #f43f5e; font-weight: 700;" title="Divergência: Triado para este motorista, mas na planilha do site está atribuído a outro entregador!">${item.motorista_entrega} ⚠️</td>`;
            }
        }
        
        return `
            <tr>
                <td>${dataHora}</td>
                <td style="font-family: monospace; font-weight: 600;">${item.codigo}</td>
                <td>${platNome}</td>
                <td style="font-weight: 600;">${item.cidade}</td>
                <td>${item.motorista}</td>
                <td><span class="status-badge ${badgeClass}">${item.status}</span></td>
                <td>${deliveryBadge}${delayWarning}</td>
                ${motoristaPlanilhaTd}
            </tr>
        `;
    }).join('');
}

// 6. GRÁFICO 1: QUANTIDADE POR CIDADES
function renderizarGraficoCidades(dados) {
    const ctx = document.getElementById('chart-cidades').getContext('2d');
    
    const contagemCidades = {};
    dados.forEach(item => {
        if (item.cidade === '---' || !item.cidade) return;
        contagemCidades[item.cidade] = (contagemCidades[item.cidade] || 0) + 1;
    });

    const labels = Object.keys(contagemCidades);
    const values = Object.values(contagemCidades);

    if (chartCidadesInst) {
        chartCidadesInst.destroy();
    }

    if (labels.length === 0) {
        chartCidadesInst = null;
        return;
    }

    chartCidadesInst = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Pacotes Triados',
                data: values,
                backgroundColor: 'rgba(56, 189, 248, 0.4)',
                borderColor: '#38bdf8',
                borderWidth: 2,
                borderRadius: 8,
                hoverBackgroundColor: 'rgba(56, 189, 248, 0.7)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f8fafc',
                    bodyColor: '#e2e8f0',
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#94a3b8' }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: {
                        color: '#94a3b8',
                        stepSize: 1
                    }
                }
            }
        }
    });
}

// 7. GRÁFICO 2: QUANTIDADE POR PLATAFORMA (EMPRESA)
function renderizarGraficoPlataformas(dados) {
    const ctx = document.getElementById('chart-plataformas').getContext('2d');
    
    const contagemPlats = {};
    dados.forEach(item => {
        const nomePlat = todasPlataformas[item.plataforma]?.nome || item.plataforma.toUpperCase();
        contagemPlats[nomePlat] = (contagemPlats[nomePlat] || 0) + 1;
    });

    const labels = Object.keys(contagemPlats);
    const values = Object.values(contagemPlats);

    if (chartPlataformasInst) {
        chartPlataformasInst.destroy();
    }

    if (labels.length === 0) {
        chartPlataformasInst = null;
        return;
    }

    const cores = [
        '#38bdf8',
        '#10b981',
        '#f59e0b',
        '#a855f7',
        '#f43f5e',
        '#3b82f6'
    ];

    chartPlataformasInst = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: cores.slice(0, labels.length).map(c => c + '33'),
                borderColor: cores.slice(0, labels.length),
                borderWidth: 1.5,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        boxWidth: 12,
                        color: '#cbd5e1'
                    }
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f8fafc',
                    bodyColor: '#e2e8f0',
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderWidth: 1
                }
            },
            cutout: '70%'
        }
    });
}

// 7. GRÁFICO 3: DESEMPENHO DE ENTREGAS POR MOTORISTA (100% STACKED BAR CHART)
function renderizarGraficoMotoristas(dados) {
    const canvas = document.getElementById('chart-motoristas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    // Filtra apenas bips com status OK (triados)
    const bipsOk = dados.filter(item => item.status === 'OK');
    
    // Agrupa por motorista
    const contagemMotoristas = {};
    bipsOk.forEach(item => {
        const mot = item.motorista || "Sem Motorista";
        if (!contagemMotoristas[mot]) {
            contagemMotoristas[mot] = {
                triados: 0,
                entregues: 0,
                em_rota: 0,
                problemas: 0,
                pendentes: 0
            };
        }
        contagemMotoristas[mot].triados += 1;
        
        const sEnt = item.status_entrega ? item.status_entrega.trim().toUpperCase() : "";
        if (sEnt === "ENTREGUE") {
            contagemMotoristas[mot].entregues += 1;
        } else if (sEnt === "EM ROTA") {
            contagemMotoristas[mot].em_rota += 1;
        } else if (sEnt === "PROBLEMA") {
            contagemMotoristas[mot].problemas += 1;
        } else {
            contagemMotoristas[mot].pendentes += 1;
        }
    });

    const motoristasLabels = Object.keys(contagemMotoristas).sort((a, b) => {
        // Ordena por maior número de pacotes triados
        return contagemMotoristas[b].triados - contagemMotoristas[a].triados;
    });

    if (chartMotoristasInst) {
        chartMotoristasInst.destroy();
    }

    if (motoristasLabels.length === 0) {
        chartMotoristasInst = null;
        return;
    }

    // Ajusta a altura da div do gráfico dinamicamente com base no número de motoristas
    const heightPerDriver = 35; // 35px por motorista
    const totalHeight = Math.max(300, motoristasLabels.length * heightPerDriver + 80);
    const containerDiv = canvas.parentElement;
    if (containerDiv) {
        containerDiv.style.height = `${totalHeight}px`;
    }

    // Prepara dados de porcentagens e valores absolutos para os datasets
    const labelComTotal = [];
    const dadosEntreguesPct = [];
    const dadosEmRotaPct = [];
    const dadosProblemasPct = [];
    const dadosPendentesPct = [];

    // Arrays para guardar os absolutos para os tooltips
    const dadosEntreguesAbs = [];
    const dadosEmRotaAbs = [];
    const dadosProblemasAbs = [];
    const dadosPendentesAbs = [];

    motoristasLabels.forEach(mot => {
        const d = contagemMotoristas[mot];
        labelComTotal.push(`${mot} (${d.triados})`);
        
        dadosEntreguesPct.push(Number(((d.entregues / d.triados) * 100).toFixed(1)));
        dadosEmRotaPct.push(Number(((d.em_rota / d.triados) * 100).toFixed(1)));
        dadosProblemasPct.push(Number(((d.problemas / d.triados) * 100).toFixed(1)));
        dadosPendentesPct.push(Number(((d.pendentes / d.triados) * 100).toFixed(1)));

        dadosEntreguesAbs.push(d.entregues);
        dadosEmRotaAbs.push(d.em_rota);
        dadosProblemasAbs.push(d.problemas);
        dadosPendentesAbs.push(d.pendentes);
    });

    chartMotoristasInst = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labelComTotal,
            datasets: [
                {
                    label: 'Entregue',
                    data: dadosEntreguesPct,
                    backgroundColor: 'rgba(16, 185, 129, 0.85)', // Verde
                    borderColor: '#10b981',
                    borderWidth: 1.5,
                    absData: dadosEntreguesAbs
                },
                {
                    label: 'Em Rota',
                    data: dadosEmRotaPct,
                    backgroundColor: 'rgba(56, 189, 248, 0.85)', // Azul
                    borderColor: '#38bdf8',
                    borderWidth: 1.5,
                    absData: dadosEmRotaAbs
                },
                {
                    label: 'Problema',
                    data: dadosProblemasPct,
                    backgroundColor: 'rgba(244, 63, 94, 0.85)', // Vermelho
                    borderColor: '#f43f5e',
                    borderWidth: 1.5,
                    absData: dadosProblemasAbs
                },
                {
                    label: 'Pendente',
                    data: dadosPendentesPct,
                    backgroundColor: 'rgba(100, 116, 139, 0.85)', // Cinza
                    borderColor: '#64748b',
                    borderWidth: 1.5,
                    absData: dadosPendentesAbs
                }
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    stacked: true,
                    max: 100,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(val) {
                            return val + '%';
                        }
                    }
                },
                y: {
                    stacked: true,
                    grid: {
                        display: false
                    },
                    ticks: {
                        color: '#cbd5e1',
                        font: {
                            weight: '700',
                            family: "'Outfit', sans-serif"
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        boxWidth: 12,
                        color: '#cbd5e1'
                    }
                },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f8fafc',
                    bodyColor: '#e2e8f0',
                    borderColor: 'rgba(255,255,255,0.08)',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            const pct = context.parsed.x;
                            const abs = context.dataset.absData[context.dataIndex];
                            return `${context.dataset.label}: ${abs} pacotes (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

// 8. LIMPAR HISTÓRICO DO SERVIDOR
async function limparHistoricoServidor() {
    if (!confirm("⚠️ ATENÇÃO: Deseja realmente excluir permanentemente todo o histórico de leituras? Esta ação não pode ser desfeita!")) {
        return;
    }

    try {
        const res = await fetch(`${API_URL}/historico/limpar`, {
            method: 'POST'
        });
        const data = await res.json();
        
        if (res.ok && data.status === 'sucesso') {
            alert(data.mensagem);
            await atualizarDados();
        } else {
            alert("Erro ao limpar dados: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha na comunicação com o servidor: " + err.message);
    }
}

// ========================================================
// LÓGICA DO MODAL DE CONFIGURAÇÕES (GERÊNCIA)
// ========================================================

// ABA CIDADES
function renderizarListaCidades() {
    todasCidades.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));

    if (todasCidades.length === 0) {
        cidadesListBody.innerHTML = '<tr><td colspan="2" style="text-align:center">Nenhuma cidade cadastrada.</td></tr>';
        motCidadeSelect.innerHTML = '<option value="">Nenhuma cidade cadastrada</option>';
        return;
    }

    cidadesListBody.innerHTML = todasCidades.map(cidade => {
        const escapedCidade = cidade.replace(/'/g, "\\'");
        return `
            <tr>
                <td style="font-weight: 600">${cidade}</td>
                <td>
                    <button class="btn-row-action" style="color: #38bdf8; margin-right: 10px;" onclick="editarCidade('${escapedCidade}')">Editar</button>
                    <button class="btn-row-action" onclick="deletarCidade('${escapedCidade}')">Deletar</button>
                </td>
            </tr>
        `;
    }).join('');

    motCidadeSelect.innerHTML = '<option value="">Selecione uma cidade...</option>' + 
        todasCidades.map(cidade => `<option value="${cidade}">${cidade}</option>`).join('');
}

async function salvarNovaCidade(e) {
    e.preventDefault();
    const cidade = cidNome.value.trim();

    if (!cidade) return;

    if (todasCidades.some(c => c.toLowerCase() === cidade.toLowerCase())) {
        alert("Esta cidade já está cadastrada.");
        return;
    }

    todasCidades.push(cidade);

    try {
        const res = await fetch(`${API_URL}/salvar-cidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cidades: todasCidades })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            cidNome.value = '';
            await recarregarConfiguracoes();
        } else {
            alert("Erro ao salvar cidade: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
}

window.editarCidade = async (cidadeAntiga) => {
    const novaCidade = prompt(`Editar nome da cidade "${cidadeAntiga}":`, cidadeAntiga);
    if (novaCidade === null) return; // Cancelou
    
    const novaCidadeTrim = novaCidade.trim();
    if (!novaCidadeTrim) {
        alert("O nome da cidade não pode ser vazio.");
        return;
    }
    
    if (novaCidadeTrim === cidadeAntiga) return; // Nenhuma alteração
    
    if (todasCidades.some(c => c.toLowerCase() === novaCidadeTrim.toLowerCase())) {
        alert("Esta cidade já está cadastrada.");
        return;
    }
    
    // Atualiza na lista de cidades
    todasCidades = todasCidades.map(c => c === cidadeAntiga ? novaCidadeTrim : c);
    
    // Atualiza no mapeamento de motoristas se existir
    let alterouMotoristas = false;
    todosMotoristas.forEach(item => {
        if (item.cidade.toLowerCase() === cidadeAntiga.toLowerCase()) {
            item.cidade = novaCidadeTrim;
            alterouMotoristas = true;
        }
    });
    
    try {
        const resCid = await fetch(`${API_URL}/salvar-cidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cidades: todasCidades })
        });
        const dataCid = await resCid.json();
        
        if (dataCid.status !== 'sucesso') {
            throw new Error(dataCid.mensagem);
        }
        
        if (alterouMotoristas) {
            const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "anjun";
            const resMot = await fetch(`${API_URL}/salvar-motoristas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motoristas: todosMotoristas, plataforma: platId })
            });
            const dataMot = await resMot.json();
            if (dataMot.status !== 'sucesso') {
                throw new Error(dataMot.mensagem);
            }
        }
        
        await recarregarConfiguracoes();
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

window.deletarCidade = async (cidade) => {
    if (!confirm(`Deseja realmente remover a cidade "${cidade}"? Isso também removerá todos os mapeamentos de motoristas associados a ela.`)) return;

    todasCidades = todasCidades.filter(c => c.toLowerCase() !== cidade.toLowerCase());

    const tamanhoOriginal = todosMotoristas.length;
    todosMotoristas = todosMotoristas.filter(item => item.cidade.toLowerCase() !== cidade.toLowerCase());
    const alterouMotoristas = (todosMotoristas.length !== tamanhoOriginal);

    try {
        const resCid = await fetch(`${API_URL}/salvar-cidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cidades: todasCidades })
        });
        const dataCid = await resCid.json();
        
        if (dataCid.status !== 'sucesso') {
            throw new Error(dataCid.mensagem);
        }

        if (alterouMotoristas) {
            const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "anjun";
            const resMot = await fetch(`${API_URL}/salvar-motoristas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motoristas: todosMotoristas, plataforma: platId })
            });
            const dataMot = await resMot.json();
            if (dataMot.status !== 'sucesso') {
                throw new Error(dataMot.mensagem);
            }
        }

        await recarregarConfiguracoes();

    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

// ABA MOTORISTAS
function renderizarListaMotoristas() {
    // Ordena alfabeticamente por Cidade e secundariamente por Motorista
    todosMotoristas.sort((a, b) => {
        const compCid = a.cidade.localeCompare(b.cidade, 'pt-BR', { sensitivity: 'base' });
        if (compCid !== 0) return compCid;
        return a.motorista.localeCompare(b.motorista, 'pt-BR', { sensitivity: 'base' });
    });

    if (todosMotoristas.length === 0) {
        motoristasListBody.innerHTML = '<tr><td colspan="3" style="text-align:center">Nenhum motorista cadastrado.</td></tr>';
        return;
    }

    motoristasListBody.innerHTML = todosMotoristas.map((item, index) => {
        return `
            <tr>
                <td style="font-weight: 600">${item.cidade}</td>
                <td>${item.motorista}</td>
                <td>
                    <button class="btn-row-action" style="color: #38bdf8; margin-right: 10px;" onclick="editarMapeamento(${index})">Editar</button>
                    <button class="btn-row-action" onclick="deletarMapeamento(${index})">Deletar</button>
                </td>
            </tr>
        `;
    }).join('');
}

async function salvarMapeamentoMotorista(e) {
    e.preventDefault();
    const cidade = motCidadeSelect.value.trim();
    const motorista = motNome.value.trim();
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "anjun";

    if (!cidade || !motorista) return;

    // Impede cadastrar exatamente o mesmo par (mesma cidade + mesmo motorista)
    const jaExiste = todosMotoristas.some(item => 
        item.cidade.toLowerCase() === cidade.toLowerCase() && 
        item.motorista.toLowerCase() === motorista.toLowerCase()
    );
    if (jaExiste) {
        alert(`O motorista "${motorista}" já está cadastrado para a cidade "${cidade}".`);
        return;
    }

    // Permite múltiplos motoristas na mesma cidade: adiciona sem substituir os demais!
    todosMotoristas.push({ cidade, motorista });

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: todosMotoristas, plataforma: platId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            motCidadeSelect.value = '';
            motNome.value = '';
            await recarregarConfiguracoes();
        } else {
            alert("Erro ao salvar motoristas: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
}

window.editarMapeamento = async (index) => {
    if (index < 0 || index >= todosMotoristas.length) return;
    const item = todosMotoristas[index];

    const novoMotorista = prompt(`Editar nome do motorista para a cidade "${item.cidade}":`, item.motorista);
    if (novoMotorista === null) return; // Cancelou
    
    const novoMotoristaTrim = novoMotorista.trim();
    if (!novoMotoristaTrim) {
        alert("O nome do motorista não pode ser vazio.");
        return;
    }
    
    if (novoMotoristaTrim === item.motorista) return; // Nenhuma alteração
    
    // Verifica se já existe outro mapeamento com essa cidade e o novo motorista
    const jaExiste = todosMotoristas.some((it, idx) => 
        idx !== index &&
        it.cidade.toLowerCase() === item.cidade.toLowerCase() && 
        it.motorista.toLowerCase() === novoMotoristaTrim.toLowerCase()
    );
    if (jaExiste) {
        alert(`O motorista "${novoMotoristaTrim}" já está cadastrado para a cidade "${item.cidade}".`);
        return;
    }
    
    item.motorista = novoMotoristaTrim;
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "anjun";
    
    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: todosMotoristas, plataforma: platId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            await recarregarConfiguracoes();
        } else {
            alert("Erro ao editar motorista: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

window.deletarMapeamento = async (index) => {
    if (index < 0 || index >= todosMotoristas.length) return;
    const item = todosMotoristas[index];

    if (!confirm(`Deseja remover o motorista "${item.motorista}" da cidade "${item.cidade}"?`)) return;

    todosMotoristas.splice(index, 1);
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "anjun";

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: todosMotoristas, plataforma: platId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            await recarregarConfiguracoes();
        } else {
            alert("Erro ao deletar motorista: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

// ABA PLATAFORMAS
function renderizarBotoesPlataformas() {
    const keys = Object.keys(todasPlataformas);
    
    platformsButtonsContainer.innerHTML = keys.map(key => {
        return `
            <button class="btn-platform-item" onclick="carregarPlataformaNoForm('${key}')">
                ${todasPlataformas[key].nome} (${key})
            </button>
        `;
    }).join('');

    if (keys.length > 0) {
        if (!platId.value) {
            carregarPlataformaNoForm(keys[0]);
        }
    } else {
        limparFormularioPlataforma();
    }
}

window.carregarPlataformaNoForm = (id) => {
    const p = todasPlataformas[id];
    if (!p) return;

    platFormTitle.innerText = `Editar Plataforma: ${p.nome}`;
    platId.value = p.id;
    
    platIdInput.value = p.id;
    platIdInput.disabled = true;
    
    platNome.value = p.nome;
    platRecebimentoUrl.value = p.recebimento_url;
    platRecebimentoInputXpath.value = p.recebimento_input_xpath;
    platRecebimentoDadosXpath.value = p.recebimento_dados_xpath;
    platAtribuicaoUrl.value = p.atribuicao_url;
    platAtribuicaoMotoristaXpath.value = p.atribuicao_motorista_xpath;
    platAtribuicaoBipXpath.value = p.atribuicao_bip_xpath;
    platLoginUser.value = p.login_usuario || "";
    platLoginPass.value = p.login_senha || "";

    const buttons = platformsButtonsContainer.querySelectorAll('.btn-platform-item');
    buttons.forEach((btn, idx) => {
        const key = Object.keys(todasPlataformas)[idx];
        if (key === id) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    btnDeletePlatform.style.display = 'block';
};

function limparFormularioPlataforma() {
    platFormTitle.innerText = "Nova Plataforma";
    platId.value = "";
    platIdInput.value = "";
    platIdInput.disabled = false;
    platNome.value = "";
    platRecebimentoUrl.value = "";
    platRecebimentoInputXpath.value = "";
    platRecebimentoDadosXpath.value = "";
    platAtribuicaoUrl.value = "";
    platAtribuicaoMotoristaXpath.value = "";
    platAtribuicaoBipXpath.value = "";
    platLoginUser.value = "";
    platLoginPass.value = "";
    
    btnDeletePlatform.style.display = 'none';

    const buttons = platformsButtonsContainer.querySelectorAll('.btn-platform-item');
    buttons.forEach(btn => btn.classList.remove('active'));
}

async function salvarConfigPlataforma(e) {
    e.preventDefault();
    const id = platIdInput.value.trim().toLowerCase().replace(/\s+/g, '');
    const nome = platNome.value.trim();

    if (!id || !nome) return;

    const payload = {
        id: id,
        nome: nome,
        recebimento_url: platRecebimentoUrl.value.trim(),
        recebimento_input_xpath: platRecebimentoInputXpath.value.trim(),
        recebimento_dados_xpath: platRecebimentoDadosXpath.value.trim(),
        atribuicao_url: platAtribuicaoUrl.value.trim(),
        atribuicao_motorista_xpath: platAtribuicaoMotoristaXpath.value.trim(),
        atribuicao_bip_xpath: platAtribuicaoBipXpath.value.trim(),
        login_usuario: platLoginUser.value.trim(),
        login_senha: platLoginPass.value.trim()
    };

    try {
        const res = await fetch(`${API_URL}/salvar-plataforma`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            alert(data.mensagem);
            await recarregarConfiguracoes();
            carregarPlataformaNoForm(id);
        } else {
            alert("Erro ao salvar plataforma: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha na comunicação com o servidor: " + err.message);
    }
}

async function deletarPlataformaServidor() {
    const id = platId.value;
    if (!id) return;
    
    if (!confirm(`Deseja realmente excluir permanentemente a plataforma ${todasPlataformas[id].nome}?`)) return;

    try {
        const res = await fetch(`${API_URL}/deletar-plataforma`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            alert(data.mensagem);
            platId.value = "";
            await recarregarConfiguracoes();
        } else {
            alert("Erro ao deletar: " + data.mensagem);
        }
    } catch (err) {
        alert("Falha na comunicação com o servidor: " + err.message);
    }
}

// --- CHECAR ALERTAS DE SEGURANÇA E DUPLICADOS PARA GERÊNCIA ---
async function checarAlertasGerencia() {
    try {
        const res = await fetch(`${API_URL}/gerencia/alertas`);
        if (res.ok) {
            const alertas = await res.json();
            const alarmOverlay = document.getElementById('alarm-overlay');
            
            if (alertas && alertas.length > 0 && alarmOverlay && alarmOverlay.style.display !== 'flex') {
                const alertInfo = alertas[0]; // Pega o primeiro alerta pendente
                
                // Popula os dados no modal
                const alarmQrCode = document.getElementById('alarm-qr-code');
                const alarmMotorista = document.getElementById('alarm-motorista');
                const alarmCidade = document.getElementById('alarm-cidade');
                const alarmTimestamp = document.getElementById('alarm-timestamp');
                
                if (alarmQrCode) alarmQrCode.innerText = alertInfo.codigo || "-";
                if (alarmMotorista) alarmMotorista.innerText = alertInfo.motorista || "-";
                if (alarmCidade) alarmCidade.innerText = alertInfo.cidade || "-";
                if (alarmTimestamp) alarmTimestamp.innerText = alertInfo.timestamp || "-";
                
                // Toca som de alerta
                try {
                    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const oscillator = audioCtx.createOscillator();
                    const gainNode = audioCtx.createGain();
                    oscillator.type = 'sawtooth';
                    oscillator.frequency.setValueAtTime(660, audioCtx.currentTime); // Frequência estridente
                    gainNode.gain.setValueAtTime(0.2, audioCtx.currentTime);
                    oscillator.connect(gainNode);
                    gainNode.connect(audioCtx.destination);
                    oscillator.start();
                    oscillator.stop(audioCtx.currentTime + 0.4);
                } catch (eAudio) {}
                
                // Exibe o overlay na tela
                alarmOverlay.style.display = 'flex';
            }
        }
    } catch (e) {
        console.error("Erro ao checar alertas da gerência:", e);
    }
}

// Configura o evento do botão de dispensar o alarme
const btnAlarmDismiss = document.getElementById('btn-alarm-dismiss');
if (btnAlarmDismiss) {
    btnAlarmDismiss.addEventListener('click', async () => {
        const alarmOverlay = document.getElementById('alarm-overlay');
        if (alarmOverlay) alarmOverlay.style.display = 'none';
        
        try {
            await fetch(`${API_URL}/gerencia/alertas/limpar`, { method: 'POST' });
            // Atualiza a tabela/gráficos imediatamente para refletir o novo log de duplicado
            await atualizarDados();
        } catch (e) {
            console.error("Erro ao limpar alertas no backend:", e);
        }
    });
}

// --- FUNÇÕES DE CONCILIAÇÃO E IMPORTAÇÃO DE ENTREGAS ---

async function processarImportacaoLocal(nomeArquivo) {
    if (!importStatusText) return;
    importStatusText.innerText = `Sincronizando arquivo local ${nomeArquivo}...`;
    importStatusText.className = 'import-status';
    
    try {
        const res = await fetch(`${API_URL}/atribuicao/importar-local`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ arquivo: nomeArquivo })
        });
        
        const resJson = await res.json();
        if (res.ok && resJson.status === 'sucesso') {
            importStatusText.innerText = `Sucesso: ${resJson.mensagem}`;
            importStatusText.className = 'import-status success';
            alert(`Sincronização concluída!\n${resJson.mensagem}`);
            await atualizarDados();
        } else {
            throw new Error(resJson.mensagem || "Erro na resposta do servidor.");
        }
    } catch (e) {
        console.error(e);
        importStatusText.innerText = `Erro: ${e.message}`;
        importStatusText.className = 'import-status error';
        alert(`Falha ao importar planilha local: ${e.message}`);
    }
}

function atualizarVisualArquivoSelecionado() {
    if (!importFile || !importStatusText) return;
    if (importFile.files && importFile.files.length > 0) {
        const file = importFile.files[0];
        importStatusText.innerText = `Arquivo carregado: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        importStatusText.className = 'import-status success';
    } else {
        importStatusText.innerText = "Nenhum arquivo selecionado";
        importStatusText.className = 'import-status';
    }
}

async function processarPlanilhaExcel() {
    if (!importFile || !importFile.files || importFile.files.length === 0) {
        alert("Por favor, selecione ou arraste uma planilha Excel (.xlsx, .xls) ou arquivo CSV primeiro.");
        return;
    }
    
    const file = importFile.files[0];
    importStatusText.innerText = "Lendo arquivo, aguarde...";
    importStatusText.className = 'import-status';
    
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const data = new Uint8Array(e.target.result);
            const workbook = XLSX.read(data, { type: 'array' });
            
            if (workbook.SheetNames.length === 0) {
                throw new Error("A planilha está vazia.");
            }
            
            const firstSheetName = workbook.SheetNames[0];
            const worksheet = workbook.Sheets[firstSheetName];
            const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });
            
            if (jsonData.length === 0) {
                throw new Error("Nenhum dado encontrado na primeira aba da planilha.");
            }
            
            // 1. Detecta cabeçalhos e colunas
            let headerRowIdx = -1;
            let colIdxCodigo = -1;
            let colIdxStatus = -1;
            let colIdxMotorista = -1;
            
            // Varre as primeiras 15 linhas para achar cabeçalhos
            for (let r = 0; r < Math.min(jsonData.length, 15); r++) {
                const row = jsonData[r];
                if (!row || !Array.isArray(row)) continue;
                
                for (let c = 0; c < row.length; c++) {
                    const cellVal = String(row[c] || '').toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim();
                    
                    // Busca coluna de código
                    if (colIdxCodigo === -1 && ['codigo', 'waybill', 'tracking', 'pacote', 'etiqueta', 'barras', 'barcode', 'pedido', 'guia', 'nombill'].some(kw => cellVal.includes(kw))) {
                        colIdxCodigo = c;
                    }
                    // Busca coluna de status
                    if (colIdxStatus === -1 && ['status', 'estado', 'situacao', 'fase', 'etapa', 'resultado'].some(kw => cellVal.includes(kw))) {
                        colIdxStatus = c;
                    }
                    // Busca coluna de motorista
                    if (colIdxMotorista === -1 && ['motorista', 'entregador', 'driver', 'courier', 'operador', 'nome'].some(kw => cellVal.includes(kw))) {
                        colIdxMotorista = c;
                    }
                }
                
                if (colIdxCodigo !== -1 && colIdxStatus !== -1) {
                    headerRowIdx = r;
                    break;
                }
            }
            
            if (colIdxCodigo === -1 || colIdxStatus === -1) {
                throw new Error("Não foi possível localizar as colunas de 'Código de Rastreamento' ou de 'Status da Entrega' na planilha. Verifique se os cabeçalhos estão bem escritos.");
            }
            
            console.log(`[Import] Cabeçalho detectado na linha ${headerRowIdx}. Coluna Código: ${colIdxCodigo}, Coluna Status: ${colIdxStatus}, Coluna Motorista: ${colIdxMotorista}`);
            
            // 2. Extrai e normaliza os dados
            const pacotesSincronizar = [];
            for (let r = headerRowIdx + 1; r < jsonData.length; r++) {
                const row = jsonData[r];
                if (!row || !row[colIdxCodigo]) continue;
                
                const codOriginal = String(row[colIdxCodigo]).trim();
                if (codOriginal.length < 5) continue;
                
                const rawStatus = String(row[colIdxStatus] || '').trim();
                const rawStatusLower = rawStatus.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
                
                // Mapeamento semântico
                let statusFinal = "PENDENTE";
                if (['entregue', 'delivered', 'concluido', 'sucesso', 'finalizado', 'entregou'].some(kw => rawStatusLower.includes(kw))) {
                    statusFinal = "ENTREGUE";
                } else if (['rota', 'transito', 'rua', 'curso', 'despachado', 'out for delivery', 'delivery', 'distribuicao', 'em andamento'].some(kw => rawStatusLower.includes(kw))) {
                    statusFinal = "EM ROTA";
                } else if (['problema', 'insucesso', 'falha', 'retornado', 'devolvido', 'anulado', 'cancelado', 'recusado', 'ausente', 'endereco', 'failure', 'returned', 'problem', 'ocorrencia', 'perda', 'roubo'].some(kw => rawStatusLower.includes(kw))) {
                    statusFinal = "PROBLEMA";
                } else if (rawStatus !== "") {
                    statusFinal = rawStatus.toUpperCase();
                }
                
                const motoristaPlanilha = colIdxMotorista !== -1 ? String(row[colIdxMotorista] || '').trim() : "";
                
                pacotesSincronizar.push({
                    codigo: codOriginal,
                    status_entrega: statusFinal,
                    motorista_entrega: motoristaPlanilha
                });
            }
            
            if (pacotesSincronizar.length === 0) {
                throw new Error("Nenhum pacote válido para conciliação foi encontrado na planilha.");
            }
            
            // 3. Envia para o servidor local salvar no SQLite
            const res = await fetch(`${API_URL}/atribuicao/atualizar-status-entrega`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(pacotesSincronizar)
            });
            
            const resJson = await res.json();
            if (res.ok && resJson.status === 'sucesso') {
                importStatusText.innerText = `Sucesso! ${resJson.mensagem}`;
                importStatusText.className = 'import-status success';
                alert(`Planilha reconciliada com sucesso!\n${resJson.mensagem}`);
                importFile.value = "";
                await atualizarDados();
            } else {
                throw new Error(resJson.mensagem || "Erro ao salvar dados no servidor.");
            }
            
        } catch (errParse) {
            console.error(errParse);
            importStatusText.innerText = `Erro: ${errParse.message}`;
            importStatusText.className = 'import-status error';
            alert(`Falha ao ler planilha: ${errParse.message}`);
        }
    };
    
    reader.onerror = () => {
        importStatusText.innerText = "Erro ao ler o arquivo selecionado.";
        importStatusText.className = 'import-status error';
    };
    
    reader.readAsArrayBuffer(file);
}

function calcularDesempenhoMotoristas(dados) {
    // Filtra apenas pacotes com status de triagem OK
    const bipsOk = dados.filter(item => item.status === 'OK');
    
    // 1. Calcula e Atualiza KPIs Globais no Topo com Split por Empresa (Anjun / iMile)
    const totalTriadosVal = bipsOk.length;
    let totalEntreguesVal = 0;
    let totalEmRotaVal = 0;
    let totalProblemasVal = 0;
    let totalPendentesVal = 0;

    let triadosAnjun = 0, triadosImile = 0;
    let entreguesAnjun = 0, entreguesImile = 0;
    let emRotaAnjun = 0, emRotaImile = 0;
    let problemasAnjun = 0, problemasImile = 0;
    let pendentesAnjun = 0, pendentesImile = 0;
    
    bipsOk.forEach(item => {
        const plat = String(item.plataforma || '').toLowerCase();
        const isAnjun = plat.includes('anjun');
        const isImile = plat.includes('imile');
        
        if (isAnjun) triadosAnjun++;
        if (isImile) triadosImile++;
        
        const sEnt = item.status_entrega ? item.status_entrega.trim().toUpperCase() : "";
        if (sEnt === "ENTREGUE") {
            totalEntreguesVal += 1;
            if (isAnjun) entreguesAnjun++;
            if (isImile) entreguesImile++;
        } else if (sEnt === "EM ROTA") {
            totalEmRotaVal += 1;
            if (isAnjun) emRotaAnjun++;
            if (isImile) emRotaImile++;
        } else if (sEnt === "PROBLEMA") {
            totalProblemasVal += 1;
            if (isAnjun) problemasAnjun++;
            if (isImile) problemasImile++;
        } else {
            totalPendentesVal += 1;
            if (isAnjun) pendentesAnjun++;
            if (isImile) pendentesImile++;
        }
    });
    
    const aproveitamentoGeralVal = totalTriadosVal > 0 ? Math.round((totalEntreguesVal / totalTriadosVal) * 100) : 0;
    const apAnjun = triadosAnjun > 0 ? Math.round((entreguesAnjun / triadosAnjun) * 100) : 0;
    const apImile = triadosImile > 0 ? Math.round((entreguesImile / triadosImile) * 100) : 0;
    
    // Atualiza Globais
    if (kpiTotalTriados) kpiTotalTriados.innerText = totalTriadosVal;
    if (kpiTotalEntregues) kpiTotalEntregues.innerText = totalEntreguesVal;
    if (kpiTotalEmRota) kpiTotalEmRota.innerText = totalEmRotaVal;
    if (kpiTotalProblemas) kpiTotalProblemas.innerText = totalProblemasVal;
    if (kpiTotalPendentes) kpiTotalPendentes.innerText = totalPendentesVal;
    if (kpiTaxaAproveitamento) kpiTaxaAproveitamento.innerText = `${aproveitamentoGeralVal}%`;

    // Atualiza Splits (Anjun e iMile)
    const setKpi = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
    };
    setKpi('kpi-triados-anjun', triadosAnjun);
    setKpi('kpi-triados-imile', triadosImile);
    setKpi('kpi-entregues-anjun', entreguesAnjun);
    setKpi('kpi-entregues-imile', entreguesImile);
    setKpi('kpi-em-rota-anjun', emRotaAnjun);
    setKpi('kpi-em-rota-imile', emRotaImile);
    setKpi('kpi-problemas-anjun', problemasAnjun);
    setKpi('kpi-problemas-imile', problemasImile);
    setKpi('kpi-pendentes-anjun', pendentesAnjun);
    setKpi('kpi-pendentes-imile', pendentesImile);
    setKpi('kpi-aproveitamento-anjun', `${apAnjun}%`);
    setKpi('kpi-aproveitamento-imile', `${apImile}%`);

    // Atualiza os minigráficos de barras empilhadas CSS nas KPIs
    const setMiniBar = (prefix, anjunVal, imileVal) => {
        const total = anjunVal + imileVal;
        const anjunSeg = document.getElementById(`${prefix}-anjun-seg`);
        const imileSeg = document.getElementById(`${prefix}-imile-seg`);
        
        if (total === 0) {
            if (anjunSeg) { anjunSeg.style.width = '0%'; anjunSeg.innerText = ''; }
            if (imileSeg) { imileSeg.style.width = '0%'; imileSeg.innerText = ''; }
            return;
        }
        
        const pctAnjun = (anjunVal / total) * 100;
        const pctImile = (imileVal / total) * 100;
        
        if (anjunSeg) {
            anjunSeg.style.width = `${pctAnjun}%`;
            anjunSeg.innerText = pctAnjun >= 20 ? anjunVal : '';
        }
        if (imileSeg) {
            imileSeg.style.width = `${pctImile}%`;
            imileSeg.innerText = pctImile >= 20 ? imileVal : '';
        }
    };

    setMiniBar('kpi-triados', triadosAnjun, triadosImile);
    setMiniBar('kpi-entregues', entreguesAnjun, entreguesImile);
    setMiniBar('kpi-em-rota', emRotaAnjun, emRotaImile);
    setMiniBar('kpi-problemas', problemasAnjun, problemasImile);
    setMiniBar('kpi-pendentes', pendentesAnjun, pendentesImile);

    const barAnjun = document.getElementById('kpi-aproveitamento-anjun-bar');
    const barImile = document.getElementById('kpi-aproveitamento-imile-bar');
    if (barAnjun) barAnjun.style.width = `${apAnjun}%`;
    if (barImile) barImile.style.width = `${apImile}%`;

    // 2. Renderiza a Tabela de Controle de Motoristas (Resumo de Desempenho)
    if (!driverPerformanceBody) return;
    
    if (totalTriadosVal === 0) {
        driverPerformanceBody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; color: #94a3b8; padding: 20px;">
                    Nenhum pacote com triagem realizada para calcular o desempenho.
                </td>
            </tr>
        `;
        if (driverSummaryBody) {
            driverSummaryBody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; color: #94a3b8; padding: 20px;">
                        Nenhum pacote triado encontrado no período selecionado.
                    </td>
                </tr>
            `;
        }
        if (driverCardsContainer) {
            driverCardsContainer.innerHTML = `
                <div class="no-drivers-placeholder">
                    Nenhum pacote triado neste período para exibir nos cartões de motoristas.
                </div>
            `;
        }
        return;
    }
    
    const performanceMap = {};
    bipsOk.forEach(item => {
        const mot = item.motorista || "Sem Motorista";
        const plat = todasPlataformas[item.plataforma]?.nome || item.plataforma.toUpperCase();
        const key = `${mot}|||${plat}`;
        
        const sEnt = item.status_entrega ? item.status_entrega.trim().toUpperCase() : "";
        const isAtrasado = (sEnt !== "ENTREGUE" && item.tempo_atraso && item.tempo_atraso >= 3.0);
        
        if (!performanceMap[key]) {
            performanceMap[key] = {
                motorista: mot,
                plataforma: plat,
                triados: 0,
                entregues: 0,
                em_rota: 0,
                problemas: 0,
                pendentes: 0,
                atrasados: 0,
                cidades: new Set()
            };
        }
        
        performanceMap[key].triados += 1;
        if (item.cidade && item.cidade !== "---" && item.cidade !== "Não Consultada" && item.cidade !== "Desconhecida" && item.cidade !== "Não Encontrada") {
            performanceMap[key].cidades.add(item.cidade);
        }
        
        if (isAtrasado) {
            performanceMap[key].atrasados += 1;
        }
        
        if (sEnt === "ENTREGUE") {
            performanceMap[key].entregues += 1;
        } else if (sEnt === "EM ROTA") {
            performanceMap[key].em_rota += 1;
        } else if (sEnt === "PROBLEMA") {
            performanceMap[key].problemas += 1;
        } else {
            performanceMap[key].pendentes += 1;
        }
    });
    
    const keys = Object.keys(performanceMap);
    
    // 2.1 Atualiza a tabela de Resumo de Triagem por Motorista (Independente de Conciliação)
    if (driverSummaryBody) {
        const sortedKeys = keys.slice().sort((a, b) => performanceMap[b].triados - performanceMap[a].triados);
        driverSummaryBody.innerHTML = sortedKeys.map(key => {
            const d = performanceMap[key];
            const cidadesList = Array.from(d.cidades).join(', ') || 'Nenhuma';
            return `
                <tr>
                    <td style="font-weight: 700; color: #f1f5f9;">${d.motorista}</td>
                    <td style="color: #94a3b8;">${d.plataforma}</td>
                    <td style="text-align: center; font-weight: 700; color: #38bdf8; font-size: 1.05rem;">${d.triados}</td>
                    <td style="color: #cbd5e1; font-size: 0.85rem; max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${cidadesList}">${cidadesList}</td>
                </tr>
            `;
        }).join('');
    }
    
    // Atualiza a tabela de reconciliação
    driverPerformanceBody.innerHTML = keys.map(key => {
        const d = performanceMap[key];
        const aproveitamentoPercent = d.triados > 0 ? Math.round((d.entregues / d.triados) * 100) : 0;
        
        let progressColor = "#f43f5e"; // Vermelho
        if (aproveitamentoPercent >= 80) {
            progressColor = "#10b981"; // Verde
        } else if (aproveitamentoPercent >= 50) {
            progressColor = "#f59e0b"; // Amarelo
        }
        
        return `
            <tr>
                <td style="font-weight: 700; color: #f1f5f9;">${d.motorista}</td>
                <td style="color: #94a3b8;">${d.plataforma}</td>
                <td style="text-align: center; font-weight: 600; color: #cbd5e1;">${d.triados}</td>
                <td style="text-align: center; font-weight: 700; color: #10b981;">${d.entregues}</td>
                <td style="text-align: center; font-weight: 600; color: #38bdf8;">${d.em_rota}</td>
                <td style="text-align: center; font-weight: 600; color: #f43f5e;">${d.problemas}</td>
                <td style="text-align: center; font-weight: 600; color: #64748b;">${d.pendentes}</td>
                <td>
                    <div class="progress-container">
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width: ${aproveitamentoPercent}%; background: ${progressColor};"></div>
                        </div>
                        <span class="progress-text">${aproveitamentoPercent}%</span>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    // 3. Renderiza a Grid de Cartões de Motoristas (com Doughnuts SVG)
    if (driverCardsContainer) {
        driverCardsContainer.innerHTML = keys.map(key => {
            const d = performanceMap[key];
            const aproveitamentoPercent = d.triados > 0 ? Math.round((d.entregues / d.triados) * 100) : 0;
            
            // Cálculo dos perímetros do Donut SVG (C = 2 * PI * r = 2 * 3.14159 * 28 = 175.9)
            const r = 28;
            const c = 2 * Math.PI * r; // ~175.93
            
            // Offset para a faixa de entregas (Verde)
            const strokeDashOffsetEntregue = c - (c * (d.entregues / d.triados));
            
            // Offset para a faixa de em rota + entregas (Amarelo)
            const strokeDashOffsetEmRota = c - (c * ((d.entregues + d.em_rota) / d.triados));

            // Calcula o tempo decorrido desde o último bip deste motorista
            const bipsMotorista = bipsOk.filter(b => (b.motorista || "Sem Motorista") === d.motorista);
            let ultimaAtividadeStr = "Sem bips";
            if (bipsMotorista.length > 0) {
                let maxTs = 0;
                bipsMotorista.forEach(b => {
                    if (b.timestamp) {
                        const ts = new Date(b.timestamp).getTime();
                        if (ts > maxTs) maxTs = ts;
                    }
                });
                
                if (maxTs > 0) {
                    const diffMs = Date.now() - maxTs;
                    const diffHrs = diffMs / (1000 * 60 * 60);
                    if (diffHrs < 1.0) {
                        const mins = Math.max(1, Math.round(diffHrs * 60));
                        ultimaAtividadeStr = `${mins}m`;
                    } else if (diffHrs < 48) {
                        const hrs = Math.floor(diffHrs);
                        const mins = Math.round((diffHrs - hrs) * 60);
                        ultimaAtividadeStr = mins > 0 ? `${hrs}h${mins.toString().padStart(2, '0')}` : `${hrs}h`;
                    } else {
                        const dias = Math.floor(diffHrs / 24);
                        ultimaAtividadeStr = `${dias} dias`;
                    }
                }
            }
            
            return `
                <div class="driver-card">
                    <div class="driver-card-header">
                        <h3>${d.motorista}</h3>
                        <span class="platform-badge">${d.plataforma}</span>
                    </div>
                    
                    <div class="driver-card-body">
                        <!-- Rosca Gráfica SVG -->
                        <div class="driver-donut-container">
                            <svg class="svg-donut" width="72" height="72">
                                <!-- Camada de Fundo (Abnormal / Pendente / Cinza) -->
                                <circle class="donut-ring" cx="36" cy="36" r="28" fill="transparent" stroke="#475569" stroke-width="6" />
                                
                                <!-- Camada de Em Rota (Amarelo) -->
                                <circle class="donut-segment" cx="36" cy="36" r="28" fill="transparent" stroke="#f59e0b" stroke-width="6" 
                                    stroke-dasharray="${c}" stroke-dashoffset="${strokeDashOffsetEmRota}" stroke-linecap="round" />
                                    
                                <!-- Camada de Entregue (Verde) -->
                                <circle class="donut-segment" cx="36" cy="36" r="28" fill="transparent" stroke="#10b981" stroke-width="6" 
                                    stroke-dasharray="${c}" stroke-dashoffset="${strokeDashOffsetEntregue}" stroke-linecap="round" />
                            </svg>
                            <!-- Texto Central -->
                            <div style="position: absolute; display: flex; flex-direction: column; align-items: center; justify-content: center;">
                                <span style="font-size: 1.15rem; font-weight: 800; color: #f8fafc; line-height: 1;">${d.triados}</span>
                                <span style="font-size: 0.6rem; color: #94a3b8; font-weight: 700; text-transform: uppercase;">Total</span>
                            </div>
                        </div>
                        
                        <!-- Legenda com Indicadores -->
                        <div class="driver-legend">
                            <div class="legend-item">
                                <span class="legend-label"><span class="legend-dot entregue"></span>Entregue</span>
                                <span class="legend-value" style="color: #10b981;">${d.entregues}</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-label"><span class="legend-dot rota"></span>Em Rota</span>
                                <span class="legend-value" style="color: #38bdf8;">${d.em_rota}</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-label"><span class="legend-dot problema"></span>Problema</span>
                                <span class="legend-value" style="color: #f43f5e;">${d.problemas}</span>
                            </div>
                            <div class="legend-item">
                                <span class="legend-label"><span class="legend-dot pendente"></span>Pendente</span>
                                <span class="legend-value" style="color: #94a3b8;">${d.pendentes}</span>
                            </div>
                            <div class="legend-item" style="border-top: 1px dashed rgba(255,255,255,0.08); padding-top: 4px; margin-top: 4px;">
                                <span class="legend-label" style="color: #f87171;"><span class="legend-dot" style="background: #ef4444;"></span>Atrasados</span>
                                <span class="legend-value" style="color: #ef4444; font-weight: 800;">${d.atrasados}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="driver-card-footer">
                        <span>Eficiência: <strong style="color: ${aproveitamentoPercent >= 80 ? '#10b981' : aproveitamentoPercent >= 50 ? '#f59e0b' : '#f43f5e'}">${aproveitamentoPercent}%</strong></span>
                        <span>Último Bip: <span class="activity-time">${ultimaAtividadeStr} atrás</span></span>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// Inicializa no carregamento e inicia o pooling de atualização de 3 em 3 segundos
window.addEventListener('load', () => {
    inicializarDashboard();
    
    // Inicia o loop de monitoramento em tempo real (Mantém o painel atualizado com novos bipes e alertas)
    setInterval(() => {
        atualizarDados();
        checarAlertasGerencia();
    }, 3000);
});
