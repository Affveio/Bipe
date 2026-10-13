// Elementos Principais do Dashboard
const input = document.getElementById('qr-input');
const statusPanel = document.getElementById('status-panel');
const statusLabel = document.getElementById('status-label');
const subStatusLabel = document.getElementById('sub-status-label');
const totalContador = document.getElementById('total-contador');
const historyLog = document.getElementById('history-log');

// Elementos de Controle do Cabeçalho
const platformSelector = document.getElementById('platform-selector');
const containerAccountSelector = document.getElementById('container-account-selector');
const accountSelector = document.getElementById('account-selector');
const containerPacoteSolto = document.getElementById('container-pacote-solto');
const btnPacoteSolto = document.getElementById('btn-pacote-solto');
const statusPacoteSolto = document.getElementById('status-pacote-solto');
const voiceSelector = document.getElementById('voice-selector');
const voiceRateSelector = document.getElementById('voice-rate-selector');
const toneSelector = document.getElementById('tone-selector');
const errorToneSelector = document.getElementById('error-tone-selector');
const divToneSelector = document.getElementById('div-tone-selector');
const containerVolumeControl = document.getElementById('container-volume-control');
const volumeSlider = document.getElementById('volume-slider');
const volumeValue = document.getElementById('volume-value');
const volumeIcon = document.getElementById('volume-icon');
const volErroSlider = document.getElementById('vol-erro-slider');
const volErroValue = document.getElementById('vol-erro-value');
const volDivergenciaSlider = document.getElementById('vol-divergencia-slider');
const volDivergenciaValue = document.getElementById('vol-divergencia-value');
const volVozSlider = document.getElementById('vol-voz-slider');
const volVozValue = document.getElementById('vol-voz-value');
const consultToggle = document.getElementById('consult-toggle');
let pacoteSoltoAtivo = (localStorage.getItem('imile_pacote_solto') === 'true');
let configVolume = parseInt(localStorage.getItem('turboscan_volume') || '250', 10);
let configVolErro = parseInt(localStorage.getItem('turboscan_vol_erro') || '300', 10);
let configVolDivergencia = parseInt(localStorage.getItem('turboscan_vol_divergencia') || '300', 10);
let configVolVoz = parseInt(localStorage.getItem('turboscan_vol_voz') || '100', 10);
let configVelVoz = parseFloat(localStorage.getItem('turboscan_vel_voz') || '1.3');
let configTom = localStorage.getItem('turboscan_tone') || 'padrao';
let configTomErro = localStorage.getItem('turboscan_tone_erro') || 'alarme_forte';
let configTomDivergencia = localStorage.getItem('turboscan_tone_divergencia') || 'sirene_divergencia';

// Elementos de Atribuição
const driverSelect = document.getElementById('driver-select');
const btnIniciarLote = document.getElementById('btn-iniciar-lote');
const btnFinalizarLote = document.getElementById('btn-finalizar-lote');
const atribuicaoStatusArea = document.getElementById('atribuicao-status-area');
const atribuicaoDriverName = document.getElementById('atribuicao-driver-name');
const atribuicaoCounter = document.getElementById('atribuicao-counter');
const atribuicaoFeedback = document.getElementById('atribuicao-feedback');
const driverCitiesListBox = document.getElementById('driver-cities-list-box');

// Elementos de Atribuição Multi-Cidades / Grupos (Exclusivo Loggi)
const containerDriverStandard = document.getElementById('container-driver-standard');
const containerLoggiCities = document.getElementById('container-loggi-cities');
const tabLoggiNovo = document.getElementById('tab-loggi-novo');
const tabLoggiExistente = document.getElementById('tab-loggi-existente');
const panelLoggiNovo = document.getElementById('panel-loggi-novo');
const panelLoggiExistente = document.getElementById('panel-loggi-existente');
const loggiCityAddSelect = document.getElementById('loggi-city-add-select');
const btnCriarGrupoAgora = document.getElementById('btn-criar-grupo-agora');
const loggiSelectedCitiesTags = document.getElementById('loggi-selected-cities-tags');
const btnLimparCidadesLoggi = document.getElementById('btn-limpar-cidades-loggi');
const btnAtualizarGruposLoggi = document.getElementById('btn-atualizar-grupos-loggi');
const filtroBuscaGrupoLoggi = document.getElementById('filtro-busca-grupo-loggi');
const loggiGrupoExistenteSelect = document.getElementById('loggi-grupo-existente-select');
const badgeGrupoLoggiAtivo = document.getElementById('badge-grupo-loggi-ativo');
const badgeGrupoLoggiTexto = document.getElementById('badge-grupo-loggi-texto');
const driverCitiesLabel = document.getElementById('driver-cities-label');
let cidadesLoggiSelecionadas = [];
let modoGrupoLoggi = 'novo';
let gruposLoggiCarregados = [];

// Elementos do Overlay de Divergência
const divergenciaOverlay = document.getElementById('divergencia-overlay');
const divergenciaTexto = document.getElementById('divergencia-texto');
const btnDestravar = document.getElementById('btn-destravar');
const divergenciasLog = document.getElementById('divergencias-log');

// Elementos do Modal de Confirmação de Motorista (Chrome Fechado / Retomada de Pendentes)
const modalConfirmarMotorista = document.getElementById('modal-confirmar-motorista');
const modalConfirmTitulo = document.getElementById('modal-confirm-titulo');
const modalConfirmSubtitulo = document.getElementById('modal-confirm-subtitulo');
const modalConfirmDesc = document.getElementById('modal-confirm-desc');
const modalConfirmPlat = document.getElementById('modal-confirm-plat');
const modalConfirmQtd = document.getElementById('modal-confirm-qtd');
const modalConfirmDriverSelect = document.getElementById('modal-confirm-driver-select');
const btnModalConfirmContinuar = document.getElementById('btn-modal-confirm-continuar');
const btnModalConfirmLimpar = document.getElementById('btn-modal-confirm-limpar');
let modalConfirmacaoAberto = false;
let confirmadoReaberturaAtivo = false;
let plataformaConfirmacaoPendente = "";

// Estado Local Compartilhado
const API_URL = (window.location.origin && window.location.origin.startsWith('http')) ? window.location.origin : 'http://127.0.0.1:5055';
let contagemSucesso = 0;
let todasPlataformas = {};
let todosMotoristas = [];
let todasCidades = [];
let plataformaAtiva = "";
let loteAtivo = false;
let sistemaTravado = false;

function normalizarMotoristas(data) {
    if (!data) return [];
    if (Array.isArray(data)) {
        return data.map(item => ({
            cidade: (item.cidade || '').trim(),
            motorista: (item.motorista || '').trim(),
            faixa_cep: (item.faixa_cep || '').trim()
        })).filter(item => item.cidade && item.motorista);
    }
    if (typeof data === 'object') {
        const lista = [];
        for (const [cidade, mot] of Object.entries(data)) {
            if (Array.isArray(mot)) {
                mot.forEach(m => {
                    if (cidade && m) lista.push({ cidade: cidade.trim(), motorista: String(m).trim(), faixa_cep: '' });
                });
            } else if (mot) {
                lista.push({ cidade: cidade.trim(), motorista: String(mot).trim(), faixa_cep: '' });
            }
        }
        return lista;
    }
    return [];
}

// FORÇA FOCO: Garante foco no leitor, EXCETO se o usuário estiver interagindo com formulários, modais, botões ou campos de texto
document.addEventListener('click', (e) => {
    // Se clicou em qualquer input de texto/busca (exceto o próprio #qr-input), permite focar e digitar normalmente
    if (
        e.target.closest('#manual-code-input') ||
        e.target.closest('#sidebar-search-input') ||
        e.target.closest('.sidebar-search-box') ||
        (e.target.closest('input') && !e.target.closest('#qr-input'))
    ) {
        return;
    }
    
    // Ignora elementos de formulário, modais, tabelas ou inputs específicos de data/configuração
    if (
        e.target.closest('select') || 
        e.target.closest('option') || 
        e.target.closest('textarea') || 
        e.target.closest('button') || 
        e.target.closest('table') || 
        e.target.closest('.table-container') || 
        e.target.closest('#modal-licenca') || 
        e.target.closest('#modal-confirmar-motorista') || 
        e.target.closest('#settings-modal') || 
        e.target.closest('#custom-prompt-modal') ||
        e.target.closest('#filter-date-start') ||
        e.target.closest('#filter-date-end') ||
        e.target.closest('#filtro-busca-grupo-loggi') ||
        modalConfirmacaoAberto || 
        (settingsModal && settingsModal.classList.contains('active'))
    ) {
        return;
    }
    
    // Em qualquer outro clique na tela (incluindo painel "AGUARDANDO BIP", fundo, etc.), garante foco no leitor
    if (input) input.focus();
});

// Auto-recuperação de foco por teclado: se o operador bipar ou teclar e o foco não estiver em um campo de texto, redireciona para o leitor
window.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    if (e.key === 'F5' || e.key === 'F12' || e.key === 'Tab' || e.key === 'Escape') return;
    if (modalConfirmacaoAberto || (settingsModal && settingsModal.classList.contains('active'))) return;
    
    const active = document.activeElement;
    const isEditing = active && (
        active.id === 'manual-code-input' ||
        active.tagName === 'TEXTAREA' ||
        (active.tagName === 'INPUT' && active.id !== 'qr-input') ||
        active.isContentEditable
    );
    
    if (!isEditing && input && document.activeElement !== input) {
        input.focus();
    }
});

// Garante foco ao voltar para a janela do aplicativo
window.addEventListener('focus', () => {
    const active = document.activeElement;
    const isEditing = active && (
        active.id === 'manual-code-input' ||
        active.tagName === 'TEXTAREA' ||
        (active.tagName === 'INPUT' && active.id !== 'qr-input')
    );
    if (!isEditing && input) {
        input.focus();
    }
});

window.addEventListener('load', () => {
    if (input) input.focus();
});

// 1. CARREGAR CONFIGURAÇÕES INICIAIS DO BACKEND
async function carregarConfiguracoes() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000);
        const modalAberto = settingsModal && (settingsModal.classList.contains('active') || settingsModal.style.display === 'flex');
        const platModal = (modalAberto && motoristaPlataformaSelect && motoristaPlataformaSelect.value) ? motoristaPlataformaSelect.value : '';
        const platParam = (platformSelector && platformSelector.value) || plataformaAtiva || platModal || '';
        const contaParam = (accountSelector && accountSelector.value) || contaSelecionadaNaSessao || '';
        const qs = new URLSearchParams({ _: String(Date.now()) });
        if (platParam) qs.set('plataforma', platParam);
        if (contaParam && contaParam !== 'padrao') qs.set('conta_id', contaParam);
        const res = await fetch(`${API_URL}/configuracoes?${qs.toString()}`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!res.ok) throw new Error("Erro ao carregar");
        
        const data = await res.json();
        todasPlataformas = data.plataformas || {};
        if (data.licenca) {
            dadosLicencaAtual = data.licenca;
            try {
                atualizarInterfaceLicenca(data.licenca);
            } catch (eLic) {
                console.warn("[Licença] Aviso ao atualizar interface:", eLic);
            }
        }
        if (platformSelector && platformSelector.value && !todasPlataformas[platformSelector.value]) {
            platformSelector.value = "";
            plataformaAtiva = "";
        }
        if (plataformaAtiva && !todasPlataformas[plataformaAtiva]) {
            plataformaAtiva = "";
        }
        todosMotoristas = normalizarMotoristas(data.motoristas);
        todasCidades = (Array.isArray(data.cidades) ? data.cidades : [])
            .map(c => String(c || '').trim())
            .filter(Boolean)
            .sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
        if (platformSelector && platformSelector.value) {
            plataformaAtiva = platformSelector.value;
        } else if (contaSelecionadaNaSessao) {
            plataformaAtiva = data.plataforma_ativa || "";
        } else if (data.plataforma_ativa) {
            try {
                const resSess = await fetch(`${API_URL}/sessao/status?plataforma=${encodeURIComponent(data.plataforma_ativa)}&_=${Date.now()}`);
                if (resSess.ok) {
                    const sessData = await resSess.json();
                    if (sessData && sessData.mensagem !== "Chrome não iniciado.") {
                        plataformaAtiva = data.plataforma_ativa;
                        contaSelecionadaNaSessao = data.conta_ativa || "padrao";
                    }
                }
            } catch (_) {}
        }
        if (consultToggle) {
            consultToggle.value = data.modo_consulta ? "ativado" : "desativado";
            consultToggle.style.color = data.modo_consulta ? "#4ade80" : "#f87171";
        }

        // Renderiza o seletor de plataforma ativa e os cards KPI inmediatamente
        atualizarSeletorPlataformas();
        renderizarCardsKpiEmpresas();

        // Carrega o histórico para sincronizar contadores e logs
        try {
            const resHist = await fetch(`${API_URL}/historico?_=${Date.now()}`);
            if (resHist.ok) {
                const histData = await resHist.json();
                // Filtra os bips com status "OK" realizados HOJE
                const hojeStr = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;
                const bipsOkHoje = histData.filter(item => {
                    const dataBip = item.timestamp ? item.timestamp.substring(0, 10) : "";
                    return item.status === "OK" && dataBip === hojeStr;
                });
                contagemSucesso = bipsOkHoje.length;
                totalContador.innerText = contagemSucesso;
                recalcularContagemEmpresas(bipsOkHoje);

                // Popula a tabela de histórico inicial do operador (apenas os de HOJE)
                historyLog.innerHTML = "";
                const bipsHoje = histData.filter(item => {
                    const dataBip = item.timestamp ? item.timestamp.substring(0, 10) : "";
                    return dataBip === hojeStr;
                });
                reconstruirDuplicadosDoHistorico(bipsHoje, true);
                const bipsExibidos = bipsHoje.slice(-150).reverse();
                if (bipsExibidos.length > 0) {
                    const ult = bipsExibidos[0];
                    atualizarCardUltimoPacote(ult.codigo, ult.cidade, ult.motorista || ult.recebedor, ult.status, ult.status === "OK" ? "badge-ok" : "badge-err");
                }
                bipsExibidos.forEach(bip => {
                    const badgeClass = bip.status === "OK" ? "badge-ok" : "badge-err";
                    const statusText = bip.status;
                    const dataHora = new Date(bip.timestamp).toLocaleTimeString('pt-BR');
                    
                    const novaLinha = document.createElement('tr');
                    novaLinha.innerHTML = `
                        <td style="color: #64748b;">${dataHora}</td>
                        <td style="font-family: monospace; cursor: pointer; transition: all 0.2s;" class="copyable-code" title="Clique para copiar (${bip.codigo})">${bip.codigo}</td>
                        <td title="${bip.cidade}">${bip.cidade}</td>
                        <td style="text-align: center;"><span class="status-badge ${badgeClass}">${statusText}</span></td>
                    `;
                    historyLog.appendChild(novaLinha);
                });
            }
        } catch (eHist) {
            console.error("Erro ao carregar histórico inicial", eHist);
        }

        // Só recupera a fila quando a plataforma e o usuário já tiverem sido selecionados
        if (plataformaAtiva && contaSelecionadaNaSessao) {
            recuperarFilaSalva();
        }
        
        atualizarSeletorMotoristas();
        sincronizarStatusLoteAtivo();
        atualizarDivergenciasPendentes();
        carregarLotesFinalizados();

    } catch (e) {
        console.error("Falha ao comunicar com o servidor. Aguardando a inicialização...", e);
        if (platformSelector && Object.keys(todasPlataformas).length === 0) {
            platformSelector.innerHTML = '<option value="">Iniciando servidor local...</option>';
        }
        setTimeout(carregarConfiguracoes, 2000);
    }
}

// Ajusta exibição do botão finalizar e do modo pacote solto baseado na plataforma ativa
function atualizarBotoesPainel() {
    const platAtual = ((platformSelector ? platformSelector.value : '') || plataformaAtiva || '').toLowerCase();
    if (btnFinalizarLote) {
        btnFinalizarLote.style.display = (platAtual === 'anjun' || platAtual === 'loggi') ? 'flex' : 'none';
    }
    atualizarVisibilidadePacoteSolto();
    atualizarSeletorContasPlataforma();
}

// 2. ATUALIZAR SELETOR DE PLATAFORMAS (DROP-DOWN)
function atualizarSeletorPlataformas() {
    const keys = Object.keys(todasPlataformas);
    if (keys.length === 0) {
        platformSelector.innerHTML = '<option value="">Nenhuma plataforma cadastrada</option>';
        return;
    }

    let optionsHtml = `<option value="" disabled ${!plataformaAtiva ? 'selected' : ''} style="color: #64748b;">Escolha a plataforma...</option>`;
    optionsHtml += keys.map(key => {
        const selected = key === plataformaAtiva ? 'selected' : '';
        return `<option value="${key}" ${selected}>${todasPlataformas[key].nome}</option>`;
    }).join('');

    platformSelector.innerHTML = optionsHtml;
    atualizarBotoesPainel();
}

// 3. SELECIONAR PLATAFORMA NO BACKEND (ABRE SELENIUM CORRESPONDENTE)
async function selecionarPlataformaNoBackend(platId) {
    statusPanel.className = 'status-container awaiting';
    statusLabel.innerText = "CARREGANDO...";
    subStatusLabel.innerText = `Abrindo o Chrome para a plataforma ${todasPlataformas[platId]?.nome || platId}`;

    try {
        const res = await fetch(`${API_URL}/selecionar-plataforma`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: platId })
        });
        const data = await res.json();
        
        if (data.status === 'sucesso') {
            plataformaAtiva = platId;
            statusPanel.className = 'status-container awaiting';
            statusLabel.innerText = "AGUARDANDO BIP";
            subStatusLabel.innerText = "Chrome pronto. Faça login se necessário e bipe!";
            await carregarConfiguracoes();
            recuperarFilaSalva();
            atualizarBotoesPainel();
        } else {
            throw new Error(data.mensagem);
        }
    } catch (e) {
        statusPanel.className = 'status-container error';
        statusLabel.innerText = "ERRO CHROMEDRIVER";
        subStatusLabel.innerText = `Erro ao inicializar browser: ${e.message}`;
        emitirBeepErro();
    }
}

// Permite selecionar a plataforma sem interferir no dropdown nativo
let _platAntesDoClick = "";
platformSelector.addEventListener('mousedown', () => {
    _platAntesDoClick = platformSelector.value || plataformaAtiva || "";
});

// Listener para alteração da Plataforma Ativa pelo usuário:
// Prepara o seletor de USUÁRIO e já carrega imediatamente os motoristas/cidades da plataforma escolhida!
platformSelector.addEventListener('change', async (e) => {
    platformSelector.blur();
    const platSelecionada = e.target.value || _platAntesDoClick;
    if (!platSelecionada) return;
    _platAntesDoClick = platSelecionada;
    plataformaAtiva = platSelecionada;
    contaSelecionadaNaSessao = "";
    _contaAntesDoClick = "";

    atualizarVisibilidadePacoteSolto();
    if (btnFinalizarLote) {
        btnFinalizarLote.style.display = (platSelecionada === 'anjun' || platSelecionada === 'loggi') ? 'flex' : 'none';
    }

    await atualizarSeletorContasPlataforma(false, false);

    try {
        const resCfg = await fetch(`${API_URL}/configuracoes?plataforma=${encodeURIComponent(platSelecionada)}&_=${Date.now()}`);
        if (resCfg.ok) {
            const cfgData = await resCfg.json();
            todosMotoristas = normalizarMotoristas(cfgData.motoristas);
            if (Array.isArray(cfgData.cidades)) {
                todasCidades = cfgData.cidades
                    .map(c => String(c || '').trim())
                    .filter(Boolean)
                    .sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            }
        } else {
            todosMotoristas = [];
        }
    } catch (_) {
        todosMotoristas = [];
    }
    atualizarSeletorMotoristas();
    carregarLotesFinalizados();
    renderizarCardsKpiEmpresas();

    statusPanel.className = 'status-container awaiting';
    statusLabel.innerText = "ESCOLHA O USUÁRIO";
    subStatusLabel.innerText = "Selecione o Usuário / Base no topo da tela para abrir o Chrome";
});

// Listener para o botão Abrir / Focar Chrome
const btnFocarChrome = document.getElementById('btn-focar-chrome');
if (btnFocarChrome) {
    btnFocarChrome.addEventListener('click', async () => {
        try {
            btnFocarChrome.style.opacity = '0.5';
            const platId = (platformSelector ? platformSelector.value : '') || plataformaAtiva || 'anjun';
            const contaId = (accountSelector ? accountSelector.value : '') || contaSelecionadaNaSessao || '';
            if (platformSelector && !platformSelector.value && platId) {
                platformSelector.value = platId;
                plataformaAtiva = platId;
                await atualizarSeletorContasPlataforma(false, true);
            }
            statusPanel.className = 'status-container awaiting';
            statusLabel.innerText = "ABRINDO CHROME...";
            subStatusLabel.innerText = `Trazendo janela do Chrome (${todasPlataformas[platId]?.nome || platId.toUpperCase()}) para a frente...`;
            const res = await fetch(`${API_URL}/focar-chrome`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plataforma: platId, conta_id: contaId })
            });
            const data = await res.json();
            if (data && data.status === 'sucesso') {
                statusPanel.className = 'status-container awaiting';
                statusLabel.innerText = "AGUARDANDO BIP";
                subStatusLabel.innerText = "Aponte o leitor para o QR Code do produto";
            }
        } catch (e) {
            console.warn("Erro ao focar Chrome:", e);
        } finally {
            setTimeout(() => { btnFocarChrome.style.opacity = '1'; }, 300);
            if (input) input.focus();
        }
    });
}

// Listener para alteração do Modo de Consulta pelo usuário
if (consultToggle) {
    consultToggle.addEventListener('change', async (e) => {
        const isAtivado = e.target.value === "ativado";
        consultToggle.style.color = isAtivado ? "#4ade80" : "#f87171";
        try {
            await fetch(`${API_URL}/configuracoes/modo-consulta`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ modo_consulta: isAtivado })
            });
        } catch (err) {
            console.error("Erro ao salvar modo de consulta:", err);
        }
    });
}

// Funções do Botão Modo Pacote Solto (Exclusivo iMile)
function renderizarBotaoPacoteSolto() {
    if (!btnPacoteSolto || !statusPacoteSolto) return;
    if (pacoteSoltoAtivo) {
        btnPacoteSolto.classList.add('ativo');
        statusPacoteSolto.className = 'btn-solto-badge badge-on';
        statusPacoteSolto.textContent = 'SIM';
        btnPacoteSolto.title = "Pacote Solto ATIVADO: O robô fará Aba 2 (Descarregamento) -> Aba 1 (Entrada) -> Aba 4 (Atribuição)";
    } else {
        btnPacoteSolto.classList.remove('ativo');
        statusPacoteSolto.className = 'btn-solto-badge badge-off';
        statusPacoteSolto.textContent = 'NÃO';
        btnPacoteSolto.title = "Pacote Solto DESATIVADO (Saca): O robô fará apenas Aba 1 (Entrada) -> Aba 4 (Atribuição)";
    }
}

function atualizarVisibilidadePacoteSolto() {
    if (!containerPacoteSolto) return;
    const plat = (platformSelector ? platformSelector.value : "") || plataformaAtiva || "";
    if (plat === 'imile') {
        containerPacoteSolto.style.display = 'flex';
        renderizarBotaoPacoteSolto();
    } else {
        containerPacoteSolto.style.display = 'none';
    }
}

if (btnPacoteSolto) {
    btnPacoteSolto.addEventListener('click', (e) => {
        e.preventDefault();
        pacoteSoltoAtivo = !pacoteSoltoAtivo;
        localStorage.setItem('imile_pacote_solto', pacoteSoltoAtivo ? 'true' : 'false');
        renderizarBotaoPacoteSolto();
        if (input) input.focus();
    });
}

// Botão Liga/Desliga Falar Cidade a cada Bipe (Topo + Modal sincronizados)
const btnFalarCidade = document.getElementById('btn-falar-cidade');
const statusFalarCidade = document.getElementById('status-falar-cidade');
const btnFalarCidadeModal = document.getElementById('btn-falar-cidade-modal');
const statusFalarCidadeModal = document.getElementById('status-falar-cidade-modal');
let falarCidadeNoBipe = (localStorage.getItem('turboscan_falar_cidade') === 'true');

function renderizarBotaoFalarCidade() {
    const pares = [
        [btnFalarCidade, statusFalarCidade],
        [btnFalarCidadeModal, statusFalarCidadeModal]
    ];
    pares.forEach(([btn, badge]) => {
        if (!btn || !badge) return;
        if (falarCidadeNoBipe) {
            btn.classList.add('ativo');
            badge.className = 'btn-solto-badge badge-on';
            badge.textContent = 'SIM';
            btn.title = "Falar Cidade ATIVADO: O sistema falará o nome da cidade em todos os bipes com sucesso";
        } else {
            btn.classList.remove('ativo');
            badge.className = 'btn-solto-badge badge-off';
            badge.textContent = 'NÃO';
            btn.title = "Falar Cidade DESATIVADO: O sistema falará apenas em alertas/divergências";
        }
    });
}
renderizarBotaoFalarCidade();

function alternarFalarCidade(e) {
    if (e) e.preventDefault();
    falarCidadeNoBipe = !falarCidadeNoBipe;
    localStorage.setItem('turboscan_falar_cidade', falarCidadeNoBipe ? 'true' : 'false');
    renderizarBotaoFalarCidade();
    if (falarCidadeNoBipe) {
        falarCidade("Falar cidade ativado");
    } else {
        falarCidade("Falar cidade desativado");
    }
    if (input) input.focus();
}

if (btnFalarCidade) btnFalarCidade.addEventListener('click', alternarFalarCidade);
if (btnFalarCidadeModal) btnFalarCidadeModal.addEventListener('click', alternarFalarCidade);


// ========================================================
// CAPTURA DO BIP E INTEGRAÇÃO DE SÍNTESE DE VOZ/SOM TURBO
// ========================================================

let globalAudioCtx = null;
let globalCompressor = null;

function getAudioContext() {
    try {
        if (!globalAudioCtx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                globalAudioCtx = new AudioContextClass();
            }
        }
        if (globalAudioCtx && globalAudioCtx.state === 'suspended') {
            globalAudioCtx.resume().catch(() => {});
        }
    } catch (_) {}
    return globalAudioCtx;
}

function getMasterOutput(audioCtx) {
    if (!audioCtx) return null;
    try {
        if (!globalCompressor) {
            globalCompressor = audioCtx.createDynamicsCompressor();
            globalCompressor.threshold.setValueAtTime(-18, audioCtx.currentTime);
            globalCompressor.knee.setValueAtTime(10, audioCtx.currentTime);
            globalCompressor.ratio.setValueAtTime(12, audioCtx.currentTime);
            globalCompressor.attack.setValueAtTime(0.001, audioCtx.currentTime);
            globalCompressor.release.setValueAtTime(0.08, audioCtx.currentTime);
            globalCompressor.connect(audioCtx.destination);
        }
        return globalCompressor;
    } catch (_) {
        return audioCtx.destination;
    }
}

// Desbloqueia o áudio imediatamente em qualquer interação do usuário/leitor de código de barras
const unlockAudio = () => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === 'suspended') {
        ctx.resume().catch(() => {});
    }
    if (window.speechSynthesis && window.speechSynthesis.paused) {
        window.speechSynthesis.resume();
    }
};
window.addEventListener('click', unlockAudio, { passive: true });
window.addEventListener('keydown', unlockAudio, { passive: true });
window.addEventListener('focus', unlockAudio, { passive: true });

// Helper para tocar pulso multi-oscilador de altíssima penetração sonora
function tocarPulsoTurbo(audioCtx, dest, freq1, freq2, freq3, startTime, duracao, ganhoPico, tipo1 = 'square', tipo2 = 'sawtooth') {
    const osc1 = audioCtx.createOscillator();
    const osc2 = audioCtx.createOscillator();
    const osc3 = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    osc1.type = tipo1;
    osc2.type = tipo2;
    osc3.type = 'square';

    osc1.frequency.setValueAtTime(freq1, startTime);
    osc2.frequency.setValueAtTime(freq2, startTime);
    osc3.frequency.setValueAtTime(freq3, startTime);

    gainNode.gain.setValueAtTime(ganhoPico, startTime);
    gainNode.gain.setValueAtTime(ganhoPico, startTime + (duracao * 0.88));
    gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duracao);

    osc1.connect(gainNode);
    osc2.connect(gainNode);
    osc3.connect(gainNode);
    gainNode.connect(dest);

    osc1.start(startTime);
    osc2.start(startTime);
    osc3.start(startTime);
    osc1.stop(startTime + duracao);
    osc2.stop(startTime + duracao);
    osc3.stop(startTime + duracao);
}

function emitirBeepSucesso() {
    if (configTom === 'mudo' || configVolume === 0) return;
    try {
        const audioCtx = getAudioContext();
        if (!audioCtx) return;
        const dest = getMasterOutput(audioCtx);
        const now = audioCtx.currentTime;
        const fatorVol = Math.max(0.05, configVolume / 100);
        const peakGain = 1.6 * fatorVol;

        const tocarNotaForte = (freqIni, freqFim, tipoPrincipal, startTime, duracao) => {
            const oscMain = audioCtx.createOscillator();
            const oscSub = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscMain.type = tipoPrincipal;
            oscSub.type = 'square';

            oscMain.frequency.setValueAtTime(freqIni, startTime);
            oscSub.frequency.setValueAtTime(freqIni * 1.5, startTime);
            if (freqFim && freqFim !== freqIni) {
                oscMain.frequency.setValueAtTime(freqFim, startTime + (duracao * 0.45));
                oscSub.frequency.setValueAtTime(freqFim * 1.5, startTime + (duracao * 0.45));
            }

            gainNode.gain.setValueAtTime(peakGain, startTime);
            gainNode.gain.setValueAtTime(peakGain, startTime + (duracao * 0.85));
            gainNode.gain.exponentialRampToValueAtTime(0.01, startTime + duracao);

            oscMain.connect(gainNode);
            oscSub.connect(gainNode);
            gainNode.connect(dest);

            oscMain.start(startTime);
            oscSub.start(startTime);
            oscMain.stop(startTime + duracao);
            oscSub.stop(startTime + duracao);
        };

        if (configTom === 'duplo') {
            tocarNotaForte(1100, 1100, 'square', now, 0.09);
            tocarNotaForte(1550, 1550, 'square', now + 0.11, 0.13);
            return;
        }

        if (configTom === 'agudo') {
            tocarNotaForte(1450, 1950, 'square', now, 0.18);
        } else if (configTom === 'grave') {
            tocarNotaForte(720, 960, 'sawtooth', now, 0.20);
        } else if (configTom === 'suave') {
            tocarNotaForte(880, 1180, 'triangle', now, 0.18);
        } else {
            tocarNotaForte(1050, 1480, 'square', now, 0.18);
        }
    } catch (e) {
        console.warn("[Audio] Falha ao emitir beep de sucesso:", e);
    }
}

// Som de Alerta / Erro Geral (Frequências de alta potência 700Hz-1850Hz audíveis de longe em qualquer caixa de som/monitor)
function emitirBeepErro() {
    if (configVolErro === 0) return;
    try {
        const audioCtx = getAudioContext();
        if (!audioCtx) return;
        const dest = getMasterOutput(audioCtx);
        const now = audioCtx.currentTime;
        const fatorVol = Math.max(0.05, configVolErro / 100);
        const peak = 2.5 * fatorVol;

        if (configTomErro === 'sirene_curta') {
            // Sirene rápida de 2 rampas fortes
            for (let i = 0; i < 2; i++) {
                const t0 = now + (i * 0.24);
                const osc1 = audioCtx.createOscillator();
                const osc2 = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc1.type = 'square';
                osc2.type = 'sawtooth';
                osc1.frequency.setValueAtTime(780, t0);
                osc1.frequency.linearRampToValueAtTime(1560, t0 + 0.12);
                osc1.frequency.linearRampToValueAtTime(780, t0 + 0.22);
                osc2.frequency.setValueAtTime(1170, t0);
                osc2.frequency.linearRampToValueAtTime(2100, t0 + 0.12);
                osc2.frequency.linearRampToValueAtTime(1170, t0 + 0.22);
                gain.gain.setValueAtTime(peak, t0);
                gain.gain.setValueAtTime(peak, t0 + 0.20);
                gain.gain.exponentialRampToValueAtTime(0.01, t0 + 0.23);
                osc1.connect(gain);
                osc2.connect(gain);
                gain.connect(dest);
                osc1.start(t0);
                osc2.start(t0);
                osc1.stop(t0 + 0.23);
                osc2.stop(t0 + 0.23);
            }
        } else if (configTomErro === 'triplo_agudo') {
            // 3 apitos agudos penetrantes (1650 Hz + 2200 Hz)
            for (let i = 0; i < 3; i++) {
                tocarPulsoTurbo(audioCtx, dest, 1550, 2150, 1050, now + (i * 0.15), 0.11, peak, 'square', 'square');
            }
        } else if (configTomErro === 'buzzer_industrial') {
            // 2 pulsos densos estilo buzina industrial de fábrica (680Hz + 1020Hz + 1360Hz)
            tocarPulsoTurbo(audioCtx, dest, 680, 1020, 1360, now, 0.22, peak, 'sawtooth', 'square');
            tocarPulsoTurbo(audioCtx, dest, 640, 960, 1280, now + 0.26, 0.26, peak, 'sawtooth', 'square');
        } else {
            // PADRAO ('alarme_forte'): 3 pulsos alternados de altíssima presença (980Hz / 740Hz / 980Hz com harmônicos em 1470Hz/1960Hz)
            tocarPulsoTurbo(audioCtx, dest, 980, 1470, 1960, now, 0.14, peak, 'square', 'sawtooth');
            tocarPulsoTurbo(audioCtx, dest, 740, 1110, 1480, now + 0.16, 0.14, peak, 'square', 'sawtooth');
            tocarPulsoTurbo(audioCtx, dest, 980, 1470, 1960, now + 0.32, 0.20, peak, 'square', 'sawtooth');
        }
    } catch (e) {
        console.warn("[Audio] Falha ao emitir som de erro:", e);
    }
}

// Som Exclusivo de Divergência / Cidade Errada (Sirene Industrial de Máxima Potência)
function emitirSomDivergencia() {
    if (configVolDivergencia === 0) return 0;
    try {
        const audioCtx = getAudioContext();
        if (!audioCtx) return 0;
        const dest = getMasterOutput(audioCtx);
        const now = audioCtx.currentTime;
        const fatorVol = Math.max(0.05, configVolDivergencia / 100);
        const peak = 2.8 * fatorVol;

        if (configTomDivergencia === 'alarme_emergencia') {
            // Sirene contínua modulada estilo emergência (0.65s)
            const osc1 = audioCtx.createOscillator();
            const osc2 = audioCtx.createOscillator();
            const osc3 = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc1.type = 'square';
            osc2.type = 'sawtooth';
            osc3.type = 'square';

            for (let c = 0; c < 3; c++) {
                const t = now + (c * 0.20);
                osc1.frequency.setValueAtTime(880, t);
                osc1.frequency.linearRampToValueAtTime(1760, t + 0.10);
                osc1.frequency.linearRampToValueAtTime(880, t + 0.20);

                osc2.frequency.setValueAtTime(1320, t);
                osc2.frequency.linearRampToValueAtTime(2200, t + 0.10);
                osc2.frequency.linearRampToValueAtTime(1320, t + 0.20);

                osc3.frequency.setValueAtTime(1760, t);
                osc3.frequency.linearRampToValueAtTime(1100, t + 0.10);
                osc3.frequency.linearRampToValueAtTime(1760, t + 0.20);
            }

            gain.gain.setValueAtTime(peak, now);
            gain.gain.setValueAtTime(peak, now + 0.56);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.62);

            osc1.connect(gain);
            osc2.connect(gain);
            osc3.connect(gain);
            gain.connect(dest);

            osc1.start(now);
            osc2.start(now);
            osc3.start(now);
            osc1.stop(now + 0.62);
            osc2.stop(now + 0.62);
            osc3.stop(now + 0.62);
            return 580;
        } else if (configTomDivergencia === 'apito_quadruplo') {
            // 4 disparos rápidos ultra-altos (1350Hz / 1850Hz)
            for (let i = 0; i < 4; i++) {
                const fBase = (i % 2 === 0) ? 1450 : 1050;
                tocarPulsoTurbo(audioCtx, dest, fBase, fBase * 1.4, fBase * 1.8, now + (i * 0.13), 0.10, peak, 'square', 'sawtooth');
            }
            return 520;
        } else if (configTomDivergencia === 'buzina_dupla') {
            // 2 buzinas graves-médias muito encorpadas de galpão
            tocarPulsoTurbo(audioCtx, dest, 750, 1125, 1500, now, 0.24, peak, 'sawtooth', 'square');
            tocarPulsoTurbo(audioCtx, dest, 680, 1020, 1360, now + 0.28, 0.28, peak, 'sawtooth', 'square');
            return 560;
        } else {
            // PADRAO ('sirene_divergencia'): 4 ciclos bitonais rápidos estilo sirene industrial (1150Hz <-> 1680Hz)
            const tempos = [
                { f1: 1200, f2: 1800, f3: 2200, dt: 0.00, dur: 0.12 },
                { f1: 820,  f2: 1230, f3: 1640, dt: 0.13, dur: 0.12 },
                { f1: 1200, f2: 1800, f3: 2200, dt: 0.26, dur: 0.12 },
                { f1: 820,  f2: 1230, f3: 1640, dt: 0.39, dur: 0.16 }
            ];
            tempos.forEach(p => {
                tocarPulsoTurbo(audioCtx, dest, p.f1, p.f2, p.f3, now + p.dt, p.dur, peak, 'square', 'sawtooth');
            });
            return 540;
        }
    } catch (e) {
        console.warn("[Audio] Falha ao emitir som de divergência:", e);
        return 0;
    }
}

// ========================================================
// CENTRAL DE VOLUMES E TESTES DE SOM (ABA VOZ & ÁUDIO)
// ========================================================
function atualizarIconeVolume(vol) {
    if (!volumeIcon) return;
    if (vol === 0) volumeIcon.innerText = '🔇';
    else if (vol < 80) volumeIcon.innerText = '🔈';
    else if (vol < 180) volumeIcon.innerText = '🔉';
    else volumeIcon.innerText = '🔊';
}

function sincronizarUICentralVolumes() {
    if (toneSelector) toneSelector.value = configTom;
    if (errorToneSelector) errorToneSelector.value = configTomErro;
    if (divToneSelector) divToneSelector.value = configTomDivergencia;
    if (voiceRateSelector) voiceRateSelector.value = String(configVelVoz);

    if (volumeSlider) volumeSlider.value = configVolume;
    if (volumeValue) volumeValue.innerText = `${configVolume}%`;
    atualizarIconeVolume(configVolume);

    if (volErroSlider) volErroSlider.value = configVolErro;
    if (volErroValue) volErroValue.innerText = `${configVolErro}%`;

    if (volDivergenciaSlider) volDivergenciaSlider.value = configVolDivergencia;
    if (volDivergenciaValue) volDivergenciaValue.innerText = `${configVolDivergencia}%`;

    if (volVozSlider) volVozSlider.value = configVolVoz;
    if (volVozValue) volVozValue.innerText = `${configVolVoz}%`;
}
sincronizarUICentralVolumes();

if (toneSelector) {
    toneSelector.addEventListener('change', (e) => {
        configTom = e.target.value;
        localStorage.setItem('turboscan_tone', configTom);
        emitirBeepSucesso();
    });
}
if (errorToneSelector) {
    errorToneSelector.addEventListener('change', (e) => {
        configTomErro = e.target.value;
        localStorage.setItem('turboscan_tone_erro', configTomErro);
        emitirBeepErro();
    });
}
if (divToneSelector) {
    divToneSelector.addEventListener('change', (e) => {
        configTomDivergencia = e.target.value;
        localStorage.setItem('turboscan_tone_divergencia', configTomDivergencia);
        emitirSomDivergencia();
    });
}
if (voiceRateSelector) {
    voiceRateSelector.addEventListener('change', (e) => {
        configVelVoz = parseFloat(e.target.value) || 1.3;
        localStorage.setItem('turboscan_vel_voz', String(configVelVoz));
        falarCidade("Velocidade da voz ajustada");
    });
}

if (volumeSlider) {
    volumeSlider.addEventListener('input', (e) => {
        configVolume = parseInt(e.target.value, 10);
        if (volumeValue) volumeValue.innerText = `${configVolume}%`;
        atualizarIconeVolume(configVolume);
        localStorage.setItem('turboscan_volume', configVolume);
    });
    volumeSlider.addEventListener('change', () => emitirBeepSucesso());
}

if (volErroSlider) {
    volErroSlider.addEventListener('input', (e) => {
        configVolErro = parseInt(e.target.value, 10);
        if (volErroValue) volErroValue.innerText = `${configVolErro}%`;
        localStorage.setItem('turboscan_vol_erro', configVolErro);
    });
    volErroSlider.addEventListener('change', () => emitirBeepErro());
}

if (volDivergenciaSlider) {
    volDivergenciaSlider.addEventListener('input', (e) => {
        configVolDivergencia = parseInt(e.target.value, 10);
        if (volDivergenciaValue) volDivergenciaValue.innerText = `${configVolDivergencia}%`;
        localStorage.setItem('turboscan_vol_divergencia', configVolDivergencia);
    });
    volDivergenciaSlider.addEventListener('change', () => emitirSomDivergencia());
}

if (volVozSlider) {
    volVozSlider.addEventListener('input', (e) => {
        configVolVoz = parseInt(e.target.value, 10);
        if (volVozValue) volVozValue.innerText = `${configVolVoz}%`;
        localStorage.setItem('turboscan_vol_voz', configVolVoz);
    });
    volVozSlider.addEventListener('change', () => falarCidade("Volume da voz ajustado"));
}

// Botões de Teste Direto na Central de Volumes
const btnTestarBipeOk = document.getElementById('btn-testar-bipe-ok');
if (btnTestarBipeOk) {
    btnTestarBipeOk.addEventListener('click', () => {
        if (configVolume === 0) {
            configVolume = 250;
            localStorage.setItem('turboscan_volume', configVolume);
            sincronizarUICentralVolumes();
        }
        emitirBeepSucesso();
    });
}

const btnTestarAlertaErro = document.getElementById('btn-testar-alerta-erro');
if (btnTestarAlertaErro) {
    btnTestarAlertaErro.addEventListener('click', () => {
        if (configVolErro === 0) {
            configVolErro = 300;
            localStorage.setItem('turboscan_vol_erro', configVolErro);
            sincronizarUICentralVolumes();
        }
        emitirBeepErro();
    });
}

const btnTestarDivergencia = document.getElementById('btn-testar-divergencia');
if (btnTestarDivergencia) {
    btnTestarDivergencia.addEventListener('click', () => {
        if (configVolDivergencia === 0) {
            configVolDivergencia = 300;
            localStorage.setItem('turboscan_vol_divergencia', configVolDivergencia);
            sincronizarUICentralVolumes();
        }
        const durSirene = emitirSomDivergencia() || 520;
        setTimeout(() => {
            falarCidade("Divergente! Pacote de outra cidade");
        }, durSirene);
    });
}

const btnTestarVoz = document.getElementById('btn-testar-voz');
if (btnTestarVoz) {
    btnTestarVoz.addEventListener('click', () => {
        if (configVolVoz === 0) {
            configVolVoz = 100;
            localStorage.setItem('turboscan_vol_voz', configVolVoz);
            sincronizarUICentralVolumes();
        }
        falarCidade("Teste de voz do sistema TurboScan. Volume em cem por cento.");
    });
}

const btnRestaurarVolumes = document.getElementById('btn-restaurar-volumes');
if (btnRestaurarVolumes) {
    btnRestaurarVolumes.addEventListener('click', () => {
        configVolume = 250;
        configVolErro = 300;
        configVolDivergencia = 300;
        configVolVoz = 100;
        configVelVoz = 1.3;
        configTom = 'padrao';
        configTomErro = 'alarme_forte';
        configTomDivergencia = 'sirene_divergencia';

        localStorage.setItem('turboscan_volume', configVolume);
        localStorage.setItem('turboscan_vol_erro', configVolErro);
        localStorage.setItem('turboscan_vol_divergencia', configVolDivergencia);
        localStorage.setItem('turboscan_vol_voz', configVolVoz);
        localStorage.setItem('turboscan_vel_voz', String(configVelVoz));
        localStorage.setItem('turboscan_tone', configTom);
        localStorage.setItem('turboscan_tone_erro', configTomErro);
        localStorage.setItem('turboscan_tone_divergencia', configTomDivergencia);

        sincronizarUICentralVolumes();
        emitirSomDivergencia();
    });
}

// Lógica do Seletor de Contas / Usuários (Anjun, iMile e Loggi)
let _contaAntesDoClick = "";
let contaSelecionadaNaSessao = "";

async function atualizarSeletorContasPlataforma(manterSelecionada = true, autoSelecionarAtiva = false) {
    if (!accountSelector || !containerAccountSelector) return;
    const platId = (platformSelector ? platformSelector.value : '') || plataformaAtiva;
    if (!platId) {
        containerAccountSelector.style.display = 'none';
        return;
    }

    try {
        const res = await fetch(`${API_URL}/plataformas/contas?_=${Date.now()}`);
        const dados = await res.json();
        const mapaContas = (dados && dados.dados) ? dados.dados : dados;
        const platInfo = mapaContas ? mapaContas[platId] : null;

        let listaContas = (platInfo && Array.isArray(platInfo.contas)) ? platInfo.contas : [];
        if (listaContas.length === 0) {
            const nomePlat = todasPlataformas[platId]?.nome || platId.toUpperCase();
            listaContas = [{ id: 'padrao', apelido: `Conta Principal (${nomePlat})` }];
        }

        containerAccountSelector.style.display = 'flex';
        let contaParaSelecionar = manterSelecionada ? contaSelecionadaNaSessao : "";
        if (!contaParaSelecionar && autoSelecionarAtiva) {
            const candidata = (platInfo && platInfo.conta_ativa) ? platInfo.conta_ativa : (listaContas[0] ? listaContas[0].id : "");
            if (candidata && listaContas.some(c => c.id === candidata)) {
                contaParaSelecionar = candidata;
            } else if (listaContas[0]) {
                contaParaSelecionar = listaContas[0].id;
            }
            if (contaParaSelecionar) {
                contaSelecionadaNaSessao = contaParaSelecionar;
            }
        }

        let opts = `<option value="" disabled ${!contaParaSelecionar ? 'selected' : ''} style="color: #64748b;">Escolha o usuário/login...</option>`;
        opts += listaContas.map(c => {
            const isSelected = (contaParaSelecionar && c.id === contaParaSelecionar) ? 'selected' : '';
            const rotulo = c.apelido || c.login_usuario || c.id;
            return `<option value="${c.id}" ${isSelected}>${rotulo}</option>`;
        }).join('');
        accountSelector.innerHTML = opts;
        accountSelector.value = contaParaSelecionar || "";
        _contaAntesDoClick = contaParaSelecionar || "";
    } catch (e) {
        console.warn("[Contas] Falha ao carregar contas da plataforma:", e);
        containerAccountSelector.style.display = 'none';
    }
}

if (accountSelector) {
    accountSelector.addEventListener('mousedown', () => {
        _contaAntesDoClick = accountSelector.value || _contaAntesDoClick;
    });

    accountSelector.addEventListener('change', async () => {
        accountSelector.blur();
        const platId = (platformSelector ? platformSelector.value : '') || plataformaAtiva;
        const contaId = accountSelector.value || _contaAntesDoClick;
        if (!platId || !contaId) return;

        contaSelecionadaNaSessao = contaId;
        _contaAntesDoClick = contaId;

        // Carrega instantaneamente (<0.1s) os motoristas exclusivos desta Base!
        if (contaId !== 'padrao') {
            try {
                const resCfgFast = await fetch(`${API_URL}/configuracoes?plataforma=${encodeURIComponent(platId)}&conta_id=${encodeURIComponent(contaId)}&_=${Date.now()}`);
                if (resCfgFast.ok) {
                    const dCfgFast = await resCfgFast.json();
                    todosMotoristas = normalizarMotoristas(dCfgFast.motoristas);
                    atualizarSeletorMotoristas();
                }
            } catch (_) {}
        }

        if (contaId === 'padrao') {
            await selecionarPlataformaNoBackend(platId);
            if (input) input.focus();
            return;
        }

        const apelido = accountSelector.options[accountSelector.selectedIndex]?.text || contaId;
        statusPanel.className = 'status-container awaiting';
        statusLabel.innerText = "ABRINDO CHROME...";
        subStatusLabel.innerText = `Iniciando navegador e conectando na conta: ${apelido}...`;

        try {
            const res = await fetch(`${API_URL}/plataformas/selecionar-conta`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plataforma: platId, conta_id: contaId })
            });
            const data = await res.json();
            if (data.status === 'sucesso') {
                plataformaAtiva = platId;
                statusLabel.innerText = "USUÁRIO ATIVO";
                subStatusLabel.innerText = `Conectado na conta: ${apelido}. Pronto para bipar!`;
                statusPanel.className = 'status-container success';
                emitirBeepSucesso();
                await carregarConfiguracoes();
                recuperarFilaSalva();
                setTimeout(() => {
                    statusPanel.className = 'status-container awaiting';
                    statusLabel.innerText = "AGUARDANDO BIP";
                    subStatusLabel.innerText = "Aponte o leitor para o QR Code do produto";
                }, 3500);
            } else {
                statusPanel.className = 'status-container error';
                statusLabel.innerText = "ERRO AO ABRIR LOGIN";
                subStatusLabel.innerText = data.mensagem || "Não foi possível abrir a conta.";
            }
        } catch (e) {
            console.error("[Contas] Erro ao selecionar conta:", e);
        } finally {
            if (input) input.focus();
        }
    });
}

let voices = [];

function popularVozes() {
    if (typeof window.speechSynthesis === 'undefined') return;
    
    voices = window.speechSynthesis.getVoices();
    // Filtra apenas vozes em português
    const vozesPt = voices.filter(v => v.lang.startsWith('pt'));
    
    if (vozesPt.length === 0) {
        voiceSelector.innerHTML = '<option value="">Voz Padrão do Sistema</option>';
        return;
    }
    
    const vozSalva = localStorage.getItem('voz_selecionada') || "";
    
    voiceSelector.innerHTML = vozesPt.map(v => {
        const selected = v.name === vozSalva ? 'selected' : '';
        return `<option value="${v.name}" ${selected}>${v.name}</option>`;
    }).join('');
    
    // Adiciona opção padrão do sistema
    voiceSelector.innerHTML += `<option value="" ${vozSalva === "" ? "selected" : ""}>Voz Padrão do Sistema</option>`;
}

// Inicializa a escuta de mudança de vozes
popularVozes();
if (typeof window.speechSynthesis !== 'undefined') {
    window.speechSynthesis.onvoiceschanged = popularVozes;
}

// Salva a preferência da voz localmente no computador do operador
voiceSelector.addEventListener('change', (e) => {
    localStorage.setItem('voz_selecionada', e.target.value);
});

function falarCidade(nomeCidade, delayMs = 220) {
    if (typeof window.speechSynthesis === 'undefined' || configVolVoz === 0) return;
    
    try {
        if (window.speechSynthesis.paused) {
            window.speechSynthesis.resume();
        }
        // Cancela qualquer fala anterior presa
        window.speechSynthesis.cancel();
    } catch (_) {}
    
    setTimeout(() => {
        try {
            if (window.speechSynthesis.paused) {
                window.speechSynthesis.resume();
            }
            const fala = new SpeechSynthesisUtterance(nomeCidade);
            fala.lang = 'pt-BR';
            fala.rate = configVelVoz || 1.3;
            fala.volume = Math.min(1.0, Math.max(0.05, configVolVoz / 100));
            
            const vozEscolhidaNome = localStorage.getItem('voz_selecionada') || (voiceSelector ? voiceSelector.value : '');
            let vozUsada = null;
            
            if (vozEscolhidaNome) {
                vozUsada = voices.find(v => v.name === vozEscolhidaNome);
                if (vozUsada) {
                    fala.voice = vozUsada;
                    fala.lang = vozUsada.lang;
                }
            }
            
            fala.onerror = (e) => {
                if (e.error === 'interrupted' || e.error === 'canceled') return;
                console.warn(`[Voz] Falha na voz principal (${e.error}). Usando voz local offline...`);
                
                try {
                    const fallback = new SpeechSynthesisUtterance(nomeCidade);
                    fallback.lang = 'pt-BR';
                    fallback.rate = configVelVoz || 1.3;
                    fallback.volume = Math.min(1.0, Math.max(0.05, configVolVoz / 100));
                    
                    const vozOffline = voices.find(v => 
                        (v.name.includes("Francisca") || v.name.includes("Antônio") || v.name.includes("Maria") || v.name.includes("Daniel") || v.name.includes("Google")) && 
                        !v.name.includes("Online")
                    );
                    if (vozOffline) {
                        fallback.voice = vozOffline;
                    }
                    window.speechSynthesis.speak(fallback);
                } catch (_) {}
            };
            
            window.speechSynthesis.speak(fala);
        } catch (e) {
            console.warn("[Voz] Erro ao sintetizar fala:", e);
        }
    }, delayMs);
}

let contagemPorEmpresaHoje = {};
let ultimoHistoricoOkCache = [];

function normalizarChavePlataforma(platRaw) {
    const p = (platRaw || '').toLowerCase().trim();
    if (!p) return '';
    if (p.includes('anjun')) return 'anjun';
    if (p.includes('imile') || p.includes('mile')) return 'imile';
    if (p.includes('loggi')) return 'loggi';
    if (p.includes('maga')) return 'magalog';
    const keys = Object.keys(todasPlataformas || {});
    for (const k of keys) {
        const nome = (todasPlataformas[k]?.nome || '').toLowerCase();
        if (p === k.toLowerCase() || (nome && p.includes(nome))) return k;
    }
    return p;
}

function recalcularContagemEmpresas(bipsOkList = null, lotesList = null) {
    if (Array.isArray(bipsOkList)) {
        ultimoHistoricoOkCache = bipsOkList;
    }
    const basePlat = (todasPlataformas && Object.keys(todasPlataformas).length > 0)
        ? todasPlataformas
        : { anjun: { nome: 'Anjun' }, imile: { nome: 'iMile' }, loggi: { nome: 'Loggi' } };

    const mapaBips = {};
    const mapaLotes = {};
    Object.keys(basePlat).forEach(k => {
        mapaBips[k] = 0;
        mapaLotes[k] = 0;
    });

    if (Array.isArray(ultimoHistoricoOkCache)) {
        ultimoHistoricoOkCache.forEach(item => {
            const k = normalizarChavePlataforma(item.plataforma);
            if (k) mapaBips[k] = (mapaBips[k] || 0) + 1;
        });
    }

    const lotesRef = Array.isArray(lotesList) ? lotesList : (Array.isArray(lotesFinalizadosCarregados) ? lotesFinalizadosCarregados : []);
    lotesRef.forEach(item => {
        const k = normalizarChavePlataforma(item.plataforma);
        const qtd = parseInt(item.quantidade, 10) || 0;
        if (k) mapaLotes[k] = (mapaLotes[k] || 0) + qtd;
    });

    const resultado = {};
    const todasChaves = new Set([...Object.keys(basePlat), ...Object.keys(mapaBips), ...Object.keys(mapaLotes)]);
    todasChaves.forEach(k => {
        if (!k) return;
        resultado[k] = Math.max(mapaBips[k] || 0, mapaLotes[k] || 0);
    });

    contagemPorEmpresaHoje = resultado;
    renderizarCardsKpiEmpresas();
}

function renderizarCardsKpiEmpresas() {
    const container = document.getElementById('kpi-platforms-container');
    if (!container) return;

    const basePlat = (todasPlataformas && Object.keys(todasPlataformas).length > 0)
        ? todasPlataformas
        : { anjun: { nome: 'Anjun' }, imile: { nome: 'iMile' }, loggi: { nome: 'Loggi' } };

    const platAtual = (platformSelector ? platformSelector.value : '') || plataformaAtiva;
    const temas = [
        { iconClass: 'kpi-icon-green', barClass: 'kpi-bar-green', icon: '🟢' },
        { iconClass: 'kpi-icon-purple', barClass: 'kpi-bar-purple', icon: '🟣' },
        { iconClass: 'kpi-icon-amber', barClass: 'kpi-bar-amber', icon: '🟠' },
        { iconClass: 'kpi-icon-blue', barClass: 'kpi-bar-blue', icon: '🔵' }
    ];

    const keys = Object.keys(basePlat).filter(k => k.toLowerCase() !== 'magalog');
    container.innerHTML = keys.map((key, idx) => {
        const info = basePlat[key] || {};
        const nomeLimpo = (info.nome || key).replace(/Express/i, '').replace(/\(Arco\)/i, '').trim().toUpperCase();
        const qtd = contagemPorEmpresaHoje[key] || 0;
        const tema = temas[idx % temas.length];
        const isAtiva = (platAtual === key);

        return `
            <div class="kpi-card ${isAtiva ? 'kpi-active-plat' : ''}" onclick="selecionarPlataformaPeloCard('${key}')" style="cursor: pointer;" title="Clique para alternar para ${info.nome || key}">
                <div class="kpi-card-top">
                    <div class="kpi-icon-box ${tema.iconClass}">🚚</div>
                    <div class="kpi-info">
                        <span class="kpi-label">${nomeLimpo}</span>
                        <span class="kpi-value" id="kpi-val-${key}">${qtd}</span>
                        <span class="kpi-sub">${isAtiva ? '● ativa agora' : 'pacotes hoje'}</span>
                    </div>
                </div>
                <div class="kpi-bar ${tema.barClass}"></div>
            </div>
        `;
    }).join('');
}

window.selecionarPlataformaPeloCard = function(platKey) {
    if (platformSelector) {
        platformSelector.value = platKey;
        platformSelector.dispatchEvent(new Event('change'));
    } else if (platKey) {
        selecionarPlataformaNoBackend(platKey);
    }
    if (input) input.focus();
};

let mapaUltimoBipePorCodigo = {};
let listaDuplicadosHoje = [];

function obterChaveStorageDuplicados() {
    const d = new Date();
    const hoje = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    return `turboscan_duplicados_${hoje}`;
}

function salvarDuplicadosLocalStorage() {
    try {
        localStorage.setItem(obterChaveStorageDuplicados(), JSON.stringify(listaDuplicadosHoje.slice(0, 120)));
    } catch (_) {}
}

function carregarDuplicadosLocalStorage() {
    try {
        const raw = localStorage.getItem(obterChaveStorageDuplicados());
        if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) return parsed;
        }
    } catch (_) {}
    return [];
}

function parsearTimestampParaMs(tsStr) {
    if (!tsStr || typeof tsStr !== 'string') return null;
    const limpo = tsStr.trim();
    const direto = Date.parse(limpo);
    if (!isNaN(direto)) return direto;
    // Formato DD/MM/YYYY HH:MM:SS
    const m = limpo.match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?/);
    if (m) {
        return new Date(
            parseInt(m[3], 10),
            parseInt(m[2], 10) - 1,
            parseInt(m[1], 10),
            parseInt(m[4], 10),
            parseInt(m[5], 10),
            parseInt(m[6] || '0', 10)
        ).getTime();
    }
    return null;
}

function formatarIntervaloSegundos(seg) {
    if (seg === null || seg === undefined || isNaN(seg) || seg < 0) return 'Repetido';
    if (seg < 60) return `+${Math.max(1, Math.round(seg))}s`;
    const min = Math.floor(seg / 60);
    const restoSeg = Math.round(seg % 60);
    if (min < 60) {
        return restoSeg > 0 ? `+${min}m${restoSeg}s` : `+${min}m`;
    }
    const horas = Math.floor(min / 60);
    const restoMin = min % 60;
    return `+${horas}h${restoMin}m`;
}

function renderizarTabelaDuplicados() {
    const tbody = document.getElementById('duplicados-log');
    const badgeCount = document.getElementById('badge-duplicados-count');
    if (badgeCount) {
        badgeCount.innerText = String(listaDuplicadosHoje.length);
    }
    if (!tbody) return;

    if (!listaDuplicadosHoje || listaDuplicadosHoje.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center; color: #64748b; padding: 22px 10px; font-style: italic; font-size: 0.76rem;">
                    Nenhum bipe duplicado hoje
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = listaDuplicadosHoje.map(item => {
        const seg = item.deltaSegundos;
        const trocouMot = Boolean(item.trocouMotorista);
        let rowClass = 'dup-row-slow';
        let pillClass = 'dup-time-slow';
        let dicaRisco = 'Alerta: Bipado após longo intervalo ou reatribuído entre motoristas (verificar pacote/etiqueta)';

        if (!trocouMot && seg !== null && seg !== undefined && seg < 10) {
            rowClass = 'dup-row-fast';
            pillClass = 'dup-time-fast';
            dicaRisco = 'Baixo risco (<10s): Provável leitura dupla acidental no gatilho do leitor';
        } else if (!trocouMot && seg !== null && seg !== undefined && seg <= 120) {
            rowClass = 'dup-row-med';
            pillClass = 'dup-time-med';
            dicaRisco = 'Atenção (10s a 2m): Pacote bipado novamente pouco tempo depois';
        }

        const tempoLabel = formatarIntervaloSegundos(seg);
        const detMotorista = item.motorista ? ` | Mot: ${item.motorista}` : '';
        const detAnt = item.motoristaAnterior && item.motoristaAnterior !== item.motorista ? ` (Antes: ${item.motoristaAnterior})` : '';

        return `
            <tr class="${rowClass}" title="${dicaRisco}${detMotorista}${detAnt}">
                <td style="white-space: nowrap; font-size: 0.76rem; color: #cbd5e1;">
                    <span>${item.hora || '---'}</span>
                    <span class="dup-time-pill ${pillClass}">${tempoLabel}</span>
                </td>
                <td style="font-family: monospace; font-weight: 800; font-size: 0.8rem; color: #f8fafc; cursor: pointer;" class="copyable-code" title="Clique para copiar (${item.codigo})">${item.codigo}</td>
                <td style="font-size: 0.78rem; color: #38bdf8; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px;" title="${item.cidade || '---'}${detMotorista}${detAnt}">
                    ${item.cidade || '---'}
                </td>
            </tr>
        `;
    }).join('');
}

function registrarEventoDuplicado({ codigo, cidade, motorista, motoristaAnterior, timestampAnterior, agoraMs }) {
    if (!codigo) return;
    const nowMs = agoraMs || Date.now();
    const horaAtual = new Date(nowMs).toLocaleTimeString('pt-BR');

    let tsAntMs = null;
    if (mapaUltimoBipePorCodigo[codigo] && mapaUltimoBipePorCodigo[codigo].tsMs) {
        tsAntMs = mapaUltimoBipePorCodigo[codigo].tsMs;
    } else if (timestampAnterior) {
        tsAntMs = parsearTimestampParaMs(timestampAnterior);
    }

    let deltaSegundos = null;
    if (tsAntMs && nowMs >= tsAntMs) {
        deltaSegundos = Math.max(1, Math.round((nowMs - tsAntMs) / 1000));
    }

    const motAnt = motoristaAnterior || (mapaUltimoBipePorCodigo[codigo] ? mapaUltimoBipePorCodigo[codigo].motorista : null);
    const motAtu = motorista || (mapaUltimoBipePorCodigo[codigo] ? mapaUltimoBipePorCodigo[codigo].motorista : null);
    const trocouMotorista = Boolean(motAnt && motAtu && motAnt.trim().toLowerCase() !== motAtu.trim().toLowerCase());

    const novoItem = {
        id: `${codigo}_${nowMs}`,
        codigo,
        cidade: cidade || (mapaUltimoBipePorCodigo[codigo] ? mapaUltimoBipePorCodigo[codigo].cidade : '---'),
        motorista: motAtu || '',
        motoristaAnterior: motAnt || '',
        hora: horaAtual,
        tsMs: nowMs,
        deltaSegundos,
        trocouMotorista
    };

    listaDuplicadosHoje.unshift(novoItem);
    if (listaDuplicadosHoje.length > 120) {
        listaDuplicadosHoje.pop();
    }
    salvarDuplicadosLocalStorage();
    renderizarTabelaDuplicados();
}

function reconstruirDuplicadosDoHistorico(bipsLista, usarStorageHoje = true) {
    mapaUltimoBipePorCodigo = {};
    const duplicadosDetectados = [];

    if (Array.isArray(bipsLista)) {
        bipsLista.forEach(bip => {
            const cod = (bip.codigo || '').trim();
            if (!cod) return;
            const tsMs = parsearTimestampParaMs(bip.timestamp) || Date.now();
            const horaStr = bip.timestamp ? new Date(tsMs).toLocaleTimeString('pt-BR') : '---';
            const cid = bip.cidade || '---';
            const mot = bip.motorista || bip.recebedor || '';
            const statusUpper = (bip.status || '').toUpperCase();
            const isStatusDup = statusUpper.includes('DUPLICADO');
            const isStatusOk = statusUpper === 'OK' || statusUpper === 'REATRIBUIDO' || isStatusDup;

            if ((mapaUltimoBipePorCodigo[cod] && isStatusOk) || isStatusDup) {
                const ant = mapaUltimoBipePorCodigo[cod];
                const deltaSegundos = (ant && ant.tsMs && tsMs >= ant.tsMs)
                    ? Math.max(1, Math.round((tsMs - ant.tsMs) / 1000))
                    : null;
                const trocouMotorista = Boolean(ant && ant.motorista && mot && ant.motorista.toLowerCase() !== mot.toLowerCase());

                duplicadosDetectados.push({
                    id: `${cod}_${tsMs}`,
                    codigo: cod,
                    cidade: cid !== '---' ? cid : (ant ? ant.cidade : '---'),
                    motorista: mot,
                    motoristaAnterior: ant ? ant.motorista : '',
                    hora: horaStr,
                    tsMs,
                    deltaSegundos,
                    trocouMotorista
                });
            }

            if (isStatusOk) {
                const infoBipe = {
                    tsMs,
                    horaStr,
                    cidade: cid,
                    motorista: mot
                };
                mapaUltimoBipePorCodigo[cod] = infoBipe;
                mapaUltimoBipePorCodigo[cod.toUpperCase()] = infoBipe;
            }
        });
    }

    if (usarStorageHoje) {
        const salvosHoje = carregarDuplicadosLocalStorage();
        const mapaUnico = new Map();
        [...salvosHoje, ...duplicadosDetectados].forEach(item => {
            if (!item || !item.codigo) return;
            const chave = `${item.codigo}_${item.hora}`;
            if (!mapaUnico.has(chave)) {
                mapaUnico.set(chave, item);
            }
        });
        listaDuplicadosHoje = Array.from(mapaUnico.values()).sort((a, b) => (b.tsMs || 0) - (a.tsMs || 0));
        salvarDuplicadosLocalStorage();
    } else {
        listaDuplicadosHoje = duplicadosDetectados.reverse();
    }

    renderizarTabelaDuplicados();
}

function atualizarCardUltimoPacote(codigo, cidade, motoristaOuObs, status, classeBadge) {
    const pillLive = document.getElementById('status-pill-indicator');
    const isErro = (classeBadge === 'badge-err' || (status && status !== 'OK'));
    if (!pillLive) return;
    if (isErro) {
        pillLive.innerText = '⚠️ Atenção no último bipe';
        pillLive.style.color = '#f87171';
        pillLive.style.borderColor = 'rgba(239, 68, 68, 0.4)';
        pillLive.style.background = 'rgba(239, 68, 68, 0.12)';
    } else {
        pillLive.innerText = '● Operação ativa';
        pillLive.style.color = '#34d399';
        pillLive.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        pillLive.style.background = 'rgba(16, 185, 129, 0.12)';
    }
}

function adicionarAoHistorico(codigo, recebedor, cidade, status, classeBadge, detalheExtra = "") {
    const agora = new Date().toLocaleTimeString('pt-BR');
    const novaLinha = document.createElement('tr');
    const statusSafe = String(status || '').replace(/"/g, '&quot;');
    const codEscaped = String(codigo || '').replace(/'/g, "\\'");
    
    novaLinha.innerHTML = `
        <td style="color: #64748b;">${agora}</td>
        <td style="font-family: monospace; white-space: nowrap;">
            <span class="copyable-code" style="cursor: pointer; transition: all 0.2s;" title="Clique para copiar (${codigo})">${codigo}</span>
            <span class="btn-filtrar-pacote" onclick="filtrarPorCodigoHistorico('${codEscaped}')" title="🔍 Filtrar todas as movimentações deste pacote (${codigo})" style="cursor: pointer; opacity: 0.6; padding: 1px 4px; border-radius: 3px; font-size: 0.72rem; margin-left: 6px;">🔍</span>
        </td>
        <td title="${cidade}">${cidade}</td>
        <td style="text-align: center;" title="${statusSafe}">
            <span class="status-badge ${classeBadge}" title="${statusSafe}" style="cursor: help;">${status}</span>
            ${detalheExtra ? `<div style="font-size: 0.66rem; color: #fbbf24; font-weight: 700; margin-top: 2px; white-space: nowrap;">🕒 ${detalheExtra}</div>` : ''}
        </td>
    `;
    
    historyLog.insertBefore(novaLinha, historyLog.firstChild);
    
    if (historyLog.children.length > 150) {
        historyLog.removeChild(historyLog.lastChild);
    }

    if (typeof filtrarTabelaHistorico === 'function') {
        const inputFiltro = document.getElementById('filtro-historico-input');
        if (inputFiltro && inputFiltro.value.trim()) {
            filtrarTabelaHistorico();
        }
    }

    atualizarCardUltimoPacote(codigo, cidade, recebedor, status, classeBadge);
}

// Fila de espera de bipes para permitir leituras seguidas e rápidas
const filaBipes = [];
let processandoFila = false;

// Função para persistir a fila atual no localStorage (segurança contra quedas de luz/PC/F5)
function salvarFilaNoLocalStorage() {
    localStorage.setItem('fila_bipes_pendentes', JSON.stringify(filaBipes));
}

// Função para recuperar a fila persistida no boot/F5
function recuperarFilaSalva() {
    try {
        const filaSalvaRaw = localStorage.getItem('fila_bipes_pendentes');
        if (filaSalvaRaw) {
            const filaSalva = JSON.parse(filaSalvaRaw);
            if (Array.isArray(filaSalva) && filaSalva.length > 0) {
                // Preenche a fila em memória
                filaBipes.length = 0;
                filaBipes.push(...filaSalva);
                console.log(`[Fila] Fila recuperada com sucesso! (${filaBipes.length} pacotes pendentes)`);

                const primeiroPendente = filaBipes[0];
                const plat = primeiroPendente.plataforma || platformSelector.value || "anjun";
                const mot = primeiroPendente.motorista;
                const temMot = Boolean(mot && mot !== "Apenas Entrada (Sem Atribuição)");

                // Se for Anjun, iMile ou Loggi e tiver motorista/destino na fila, abre o Chrome primeiro e solicita confirmação
                if ((plat === 'anjun' || plat === 'imile' || plat === 'loggi') && temMot) {
                    prepararSessaoEMostrarConfirmacao(mot, plat, filaBipes.length, true);
                    return;
                }
                
                // Exibe feedback temporário na tela e começa a rodar
                statusPanel.className = 'status-container awaiting';
                statusLabel.innerText = "RETOMANDO FILA...";
                subStatusLabel.innerText = `Recuperados ${filaBipes.length} pacotes pendentes do localStorage. Processando...`;
                
                if (!processandoFila) {
                    processarProximoDaFila();
                }
            }
        }
    } catch (e) {
        console.error("Erro ao recuperar fila do localStorage:", e);
    }
}

async function processarProximoDaFila() {
    if (filaBipes.length === 0) {
        processandoFila = false;
        // Volta para o estado inicial após 4 segundos se nada for bipado
        setTimeout(() => {
            if (filaBipes.length === 0 && !processandoFila) {
                statusPanel.className = 'status-container awaiting';
                statusLabel.innerText = "AGUARDANDO BIP";
                subStatusLabel.innerText = "Aponte o leitor para o QR Code do produto";
            }
        }, 4000);
        return;
    }

    processandoFila = true;
    const { codigo, plataforma, motorista, cidades_selecionadas, pacote_solto } = filaBipes[0]; // Apenas lê o primeiro da fila (remove após processar)
    const filaRestante = filaBipes.length - 1;
    const textoFila = filaRestante > 0 ? ` [Fila: ${filaRestante} pendente(s)]` : '';

    const codKeyUpper = String(codigo || '').trim().toUpperCase();
    const regDupLocal = mapaUltimoBipePorCodigo[codigo] || mapaUltimoBipePorCodigo[codKeyUpper];

    statusPanel.className = 'status-container awaiting';
    statusLabel.innerText = "PROCESSANDO...";
    subStatusLabel.innerText = `Analisando pacote ${codigo}${textoFila}`;

    if (motorista) {
        atribuicaoFeedback.innerText = `Atribuindo pacote ${codigo}...`;
        atribuicaoFeedback.style.color = "#38bdf8";
    }

    try {
        const payloadBip = JSON.stringify({ 
            codigo: codigo, 
            plataforma: plataforma, 
            motorista: motorista,
            cidades_selecionadas: (cidades_selecionadas && cidades_selecionadas.length > 0) ? cidades_selecionadas : (motorista ? [motorista] : []),
            pacote_solto: Boolean(pacote_solto),
            confirmado_reabertura: confirmadoReaberturaAtivo
        });
        let resposta;
        try {
            resposta = await fetch(`${API_URL}/bip`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payloadBip
            });
        } catch (errFetch1) {
            await new Promise(r => setTimeout(r, 350));
            resposta = await fetch(`${API_URL}/bip`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payloadBip
            });
        }

        const resultado = await resposta.json();

        if (resposta.ok && resultado.status === 'sucesso') {
            confirmadoReaberturaAtivo = false;
            const isDup = Boolean(resultado.duplicado === true || regDupLocal);
            
            if (isDup) {
                const motAlvoDup = resultado.motorista || motorista;
                const horaAntDup = resultado.timestamp_anterior || (regDupLocal && regDupLocal.horaStr) || '---';
                statusPanel.className = 'status-container error';
                statusLabel.innerText = "DUPLICADO";
                if (motAlvoDup && motAlvoDup !== 'Sem Motorista') {
                    subStatusLabel.innerText = `⚠️ Atribuído para ${motAlvoDup} (Já bipado às ${horaAntDup})${textoFila}`;
                } else {
                    subStatusLabel.innerText = `⚠️ Pacote já bipado anteriormente às ${horaAntDup}${textoFila}`;
                }
                emitirBeepErro();
                if (resultado.auto_atribuido && motAlvoDup && motAlvoDup !== 'Sem Motorista') {
                    falarCidade(`Pacote duplicado, atribuindo para o motorista ${motAlvoDup}`);
                } else {
                    falarCidade("Pacote duplicado");
                }
            } else if (resultado.auto_atribuido) {
                statusPanel.className = 'status-container success';
                statusLabel.innerText = resultado.cidade || "AUTO-ATRIBUÍDO";
                subStatusLabel.innerText = `📍 Auto-atribuído ➔ Grupo Aberto: ${resultado.motorista}${textoFila}`;
                emitirBeepSucesso();
                const cidAuto = (resultado.cidade && resultado.cidade !== '---' && resultado.cidade !== 'Anjun' && resultado.cidade !== 'Não Consultada' && !resultado.cidade.includes('Não Informada')) ? `${resultado.cidade}, ` : '';
                falarCidade(`${cidAuto}atribuindo para o motorista ${resultado.motorista}`);
            } else if (resultado.cidade && resultado.cidade.includes('Não Informada')) {
                statusPanel.className = 'status-container success';
                statusLabel.innerText = "SEM RETORNO DE CIDADE";
                subStatusLabel.innerText = `⚠️ Atribuído (Site não informou cidade/CEP — confira na etiqueta)${textoFila}`;
                emitirBeepSucesso();
                falarCidade("Atenção: pacote atribuído sem retorno de cidade");
            } else {
                statusPanel.className = 'status-container success';
                statusLabel.innerText = resultado.cidade;
                subStatusLabel.innerText = `Recebedor: ${resultado.recebedor}${textoFila}`;
                emitirBeepSucesso();
                if (falarCidadeNoBipe && resultado.cidade && resultado.cidade !== '---' && resultado.cidade !== 'Não Consultada') {
                    falarCidade(resultado.cidade);
                }
            }
            
            // Se for duplicado e já tiver sido bipado hoje, não incrementa para não duplicar contagem do dia
            const hojeStr = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;
            const hojeBR = `${String(new Date().getDate()).padStart(2, '0')}/${String(new Date().getMonth() + 1).padStart(2, '0')}/${new Date().getFullYear()}`;
            const jaBipadoHoje = Boolean(isDup && (regDupLocal || (resultado.timestamp_anterior && (resultado.timestamp_anterior.includes(hojeStr) || resultado.timestamp_anterior.includes(hojeBR)))));

            const platAtual = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
            if (!jaBipadoHoje) {
                contagemSucesso++;
                totalContador.innerText = contagemSucesso;
                const kPlat = normalizarChavePlataforma(platAtual);
                if (kPlat) {
                    contagemPorEmpresaHoje[kPlat] = (contagemPorEmpresaHoje[kPlat] || 0) + 1;
                    renderizarCardsKpiEmpresas();
                }
            }
            
            const badgeTipo = isDup ? "badge-err" : (resultado.auto_atribuido ? "badge-proc" : "badge-ok");
            const statusTextoHist = isDup ? "DUPLICADO" : "OK";
            const obsHistorico = isDup ? "DUPLICADO" : (resultado.auto_atribuido ? `Auto: ${resultado.motorista}` : resultado.recebedor);
            const agoraMs = Date.now();
            if (isDup) {
                registrarEventoDuplicado({
                    codigo,
                    cidade: resultado.cidade || (regDupLocal && regDupLocal.cidade) || '---',
                    motorista: resultado.motorista || motorista || (regDupLocal && regDupLocal.motorista) || '',
                    motoristaAnterior: resultado.motorista_anterior || (regDupLocal && regDupLocal.motorista) || '',
                    timestampAnterior: resultado.timestamp_anterior || (regDupLocal && regDupLocal.horaStr) || '',
                    agoraMs
                });
            }
            const infoOk = {
                tsMs: agoraMs,
                horaStr: new Date(agoraMs).toLocaleTimeString('pt-BR'),
                cidade: resultado.cidade || '---',
                motorista: resultado.motorista || motorista || ''
            };
            mapaUltimoBipePorCodigo[codigo] = infoOk;
            mapaUltimoBipePorCodigo[codKeyUpper] = infoOk;
            adicionarAoHistorico(codigo, obsHistorico, resultado.cidade, statusTextoHist, badgeTipo);

            if (motorista || platAtual === 'loggi') {
                let textCount = `${resultado.contagem} PACOTES BIPADOS`;
                if (resultado.contagem_site !== null && resultado.contagem_site !== undefined) {
                    textCount += ` (Site: ${resultado.contagem_site})`;
                }
                atribuicaoCounter.innerText = textCount;
                if (platAtual === 'loggi' && resultado.motorista) {
                    const activeNameEl = document.getElementById('active-driver-name-display');
                    if (activeNameEl) activeNameEl.innerText = resultado.motorista;
                    if (badgeGrupoLoggiTexto) badgeGrupoLoggiTexto.innerText = resultado.motorista;
                }
                const nomeAlvo = resultado.motorista || motorista || "lote";
                if (isDup) {
                    atribuicaoFeedback.innerText = `[Aviso] Pacote Duplicado! Atribuído para ${nomeAlvo}.`;
                    atribuicaoFeedback.style.color = "#fbbf24"; // Amarelo
                } else if (resultado.auto_atribuido) {
                    atribuicaoFeedback.innerText = `Auto-atribuído para ${resultado.motorista} (${resultado.contagem_motorista} no grupo aberto).`;
                    atribuicaoFeedback.style.color = "#34d399"; // Verde esmeralda
                } else {
                    atribuicaoFeedback.innerText = `Sucesso! Pacote ${codigo} atribuído a ${nomeAlvo}.`;
                    atribuicaoFeedback.style.color = "#4ade80"; // Verde
                }
            }
        } else if (resultado.status === 'finalizado_limite') {
            statusPanel.className = 'status-container success';
            statusLabel.innerText = resultado.cidade;
            subStatusLabel.innerText = `Recebedor: ${resultado.recebedor}${textoFila}`;
            emitirBeepSucesso();
            
            const isDupLim = resultado.duplicado === true;
            const hojeStr = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;
            const hojeBR = `${String(new Date().getDate()).padStart(2, '0')}/${String(new Date().getMonth() + 1).padStart(2, '0')}/${new Date().getFullYear()}`;
            const jaBipadoHojeLim = Boolean(isDupLim && resultado.timestamp_anterior && (resultado.timestamp_anterior.includes(hojeStr) || resultado.timestamp_anterior.includes(hojeBR)));

            if (!jaBipadoHojeLim) {
                contagemSucesso++;
                totalContador.innerText = contagemSucesso;
                const kPlatLim = normalizarChavePlataforma((platformSelector ? platformSelector.value : "") || plataformaAtiva);
                if (kPlatLim) {
                    contagemPorEmpresaHoje[kPlatLim] = (contagemPorEmpresaHoje[kPlatLim] || 0) + 1;
                    renderizarCardsKpiEmpresas();
                }
            }
            
            const agoraLimMs = Date.now();
            if (isDupLim || mapaUltimoBipePorCodigo[codigo] || mapaUltimoBipePorCodigo[codKeyUpper]) {
                registrarEventoDuplicado({
                    codigo,
                    cidade: resultado.cidade,
                    motorista: resultado.motorista || motorista,
                    motoristaAnterior: resultado.motorista_anterior,
                    timestampAnterior: resultado.timestamp_anterior,
                    agoraMs: agoraLimMs
                });
            }
            const infoLim = {
                tsMs: agoraLimMs,
                horaStr: new Date(agoraLimMs).toLocaleTimeString('pt-BR'),
                cidade: resultado.cidade || '---',
                motorista: resultado.motorista || motorista || ''
            };
            mapaUltimoBipePorCodigo[codigo] = infoLim;
            mapaUltimoBipePorCodigo[codKeyUpper] = infoLim;
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "OK", "badge-ok");

            if (motorista || resultado.motorista) {
                const motNome = resultado.motorista || motorista;
                atribuicaoCounter.innerText = `0 PACOTES BIPADOS`;
                atribuicaoFeedback.innerText = `Lote de 200 concluído! Iniciado novo lote para ${motNome}...`;
                atribuicaoFeedback.style.color = "#38bdf8";
                falarCidade(`Lote de 200 concluído para ${motNome}`);
                carregarLotesFinalizados();
            }
        } else if (resultado.status === 'divergente') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "DIVERGENTE";
            
            const durSirene = emitirSomDivergencia() || 500;
            const cidadePacote = (resultado.cidade && resultado.cidade !== '---' && resultado.cidade !== 'Não Consultada') ? resultado.cidade : '';
            if (cidadePacote) {
                subStatusLabel.innerText = `Pacote de: ${cidadePacote} | Esperado: ${resultado.motorista_esperado}${textoFila}`;
                falarCidade(`Divergente! Pacote de ${cidadePacote}`, durSirene);
            } else {
                subStatusLabel.innerText = `Destinado a: ${resultado.motorista_esperado}${textoFila}`;
                falarCidade(`Divergente! Pertence ao motorista ${resultado.motorista_esperado}`, durSirene);
            }
            
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "DIVERGENTE", "badge-err");
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Falha: ${resultado.mensagem}`;
                atribuicaoFeedback.style.color = "#f87171";
            }
            
            // Fluxo contínuo sem bloqueio de tela: emite alerta visual e sonoro/voz sem travar o leitor
            // travarSistemaDivergencia(codigo, resultado.cidade, resultado.motorista_esperado, motorista);

        } else if (resultado.status === 'fora_de_rota') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "FORA DA BASE";
            subStatusLabel.innerText = `${resultado.mensagem}${textoFila}`;
            
            const durSirene = emitirSomDivergencia() || 500;
            falarCidade("Pacote não pertence a esta Base", durSirene);
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "FORA DA BASE", "badge-err");
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Falha: ${resultado.mensagem}`;
                atribuicaoFeedback.style.color = "#f87171";
            }
        } else if (resultado.status === 'erro_sem_entrada') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "SEM ENTRADA";
            subStatusLabel.innerText = `${resultado.mensagem}${textoFila}`;
            
            emitirBeepErro();
            falarCidade("Pacote sem entrada", 420);
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "SEM ENTRADA", "badge-err");
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Falha: ${resultado.mensagem}`;
                atribuicaoFeedback.style.color = "#f87171";
            }
            
            // Trava a tela com o aviso de sem entrada
            travarSistemaSemEntrada(codigo, resultado.mensagem);
        } else if (resultado.status === 'duplicado') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "DUPLICADO";
            
            let horaFormatadaPrimeiroBipe = "";
            const tsAnt = resultado.timestamp || resultado.timestamp_anterior;
            if (tsAnt) {
                if (tsAnt.includes("T")) {
                    const partes = tsAnt.split("T");
                    horaFormatadaPrimeiroBipe = partes[1].substring(0, 8);
                } else if (tsAnt.includes(" ")) {
                    const partes = tsAnt.split(" ");
                    horaFormatadaPrimeiroBipe = partes[1].substring(0, 8);
                } else {
                    horaFormatadaPrimeiroBipe = tsAnt.substring(0, 8);
                }
            }
            
            const avisoHora = horaFormatadaPrimeiroBipe ? ` às ${horaFormatadaPrimeiroBipe}` : "";
            const motAnterior = resultado.motorista_anterior || resultado.motorista || "outro motorista";
            subStatusLabel.innerText = `⛔ Já bipado${avisoHora} para ${motAnterior}${textoFila}`;
            
            emitirBeepErro();
            falarCidade("Pacote duplicado", 420);
            const agoraDupRespMs = Date.now();
            registrarEventoDuplicado({
                codigo,
                cidade: resultado.cidade,
                motorista: motorista || resultado.motorista,
                motoristaAnterior: motAnterior,
                timestampAnterior: tsAnt,
                agoraMs: agoraDupRespMs
            });
            const infoDupResp = {
                tsMs: agoraDupRespMs,
                horaStr: new Date(agoraDupRespMs).toLocaleTimeString('pt-BR'),
                cidade: resultado.cidade || '---',
                motorista: motAnterior
            };
            mapaUltimoBipePorCodigo[codigo] = infoDupResp;
            mapaUltimoBipePorCodigo[codKeyUpper] = infoDupResp;
            
            const detalheDup = horaFormatadaPrimeiroBipe ? `1º às ${horaFormatadaPrimeiroBipe}` : "";
            adicionarAoHistorico(codigo, "---", resultado.cidade, "DUPLICADO", "badge-err", detalheDup);
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Duplicado: 1º bipe${avisoHora} (${motAnterior})`;
                atribuicaoFeedback.style.color = "#f87171";
            }
            
            // Alerta visual/sonoro em vermelho sem bloquear a tela (igual divergência)
            // travarSistemaDuplicado(codigo, resultado.timestamp, resultado.motorista, resultado.cidade);
        } else if (resultado.status === 'chrome_fechado') {
            processandoFila = false;
            await prepararSessaoEMostrarConfirmacao(motorista, plataforma, filaBipes.length, false);
            return;
        } else if (resultado.status === 'aguardando_login') {
            processandoFila = false;
            const plat = resultado.plataforma || plataforma || 'anjun';
            const platLow = plat.toLowerCase();
            const isLoggi = platLow.includes('loggi');
            const isImile = platLow.includes('imile');
            
            // Proteção contra loop infinito no mesmo pacote
            const itemAtual = filaBipes[0];
            if (itemAtual) {
                itemAtual.tentativasLogin = (itemAtual.tentativasLogin || 0) + 1;
                if (itemAtual.tentativasLogin >= 3) {
                    filaBipes.shift();
                    salvarFilaNoLocalStorage();
                    esconderOverlayAguardandoLogin();
                    if (monitoramentoLoginInterval) {
                        clearInterval(monitoramentoLoginInterval);
                        monitoramentoLoginInterval = null;
                    }
                    statusPanel.className = 'status-container error';
                    statusLabel.innerText = "SESSÃO DESCONECTADA";
                    subStatusLabel.innerText = "Faça login no Chrome e bipe o pacote novamente.";
                    emitirBeepErro();
                    falarCidade("Sessão desconectada. Faça login no Chrome.");
                    return;
                }
            }

            if (!monitoramentoLoginInterval) {
                if (isLoggi) {
                    falarCidade("Atenção: Sessão da Loggi desconectada. Clique em Entrar com o Google no Chrome");
                } else if (isImile) {
                    falarCidade("Atenção: Sessão da iMile desconectada. Faça o login no Chrome");
                } else {
                    falarCidade("Atenção: Sessão da Anjun desconectada. Resolva o não sou robô no Chrome");
                }
                emitirBeepErro();
            }
            mostrarOverlayAguardandoLogin(resultado.mensagem, plat);
            iniciarMonitoramentoLogin(plat);
            return;
        } else {
            throw new Error(resultado.mensagem || "Erro na triagem");
        }
    } catch (erro) {
        const msgErro = String(erro.message || "").toLowerCase();
        const platAlvo = plataforma || platformSelector.value || "anjun";
        const temMot = Boolean(motorista && motorista !== "Apenas Entrada (Sem Atribuição)");
        if ((platAlvo === 'anjun' || platAlvo === 'imile' || platAlvo === 'loggi') && temMot &&
            (msgErro.includes("chrome") || msgErro.includes("fechado") || msgErro.includes("comunicação") || msgErro.includes("failed to fetch") || msgErro.includes("networkerror") || msgErro.includes("load failed"))) {
            processandoFila = false;
            await prepararSessaoEMostrarConfirmacao(motorista, platAlvo, filaBipes.length, false);
            return;
        }
        if (msgErro.includes("não sou robô") || msgErro.includes("nao sou robo") || (msgErro.includes("sessão") && (msgErro.includes("expirad") || msgErro.includes("desconectad"))) || (platAlvo === 'loggi' && (msgErro.includes("entrar com o google") || msgErro.includes("acesse o arco") || msgErro.includes("login")))) {
            processandoFila = false;
            const platLow = platAlvo.toLowerCase();
            const isLoggi = platLow.includes('loggi');
            const isImile = platLow.includes('imile');
            
            const itemAtual = filaBipes[0];
            if (itemAtual) {
                itemAtual.tentativasLogin = (itemAtual.tentativasLogin || 0) + 1;
                if (itemAtual.tentativasLogin >= 3) {
                    filaBipes.shift();
                    salvarFilaNoLocalStorage();
                    esconderOverlayAguardandoLogin();
                    if (monitoramentoLoginInterval) {
                        clearInterval(monitoramentoLoginInterval);
                        monitoramentoLoginInterval = null;
                    }
                    statusPanel.className = 'status-container error';
                    statusLabel.innerText = "SESSÃO DESCONECTADA";
                    subStatusLabel.innerText = "Faça login no Chrome e bipe o pacote novamente.";
                    emitirBeepErro();
                    falarCidade("Sessão desconectada. Faça login no Chrome.");
                    return;
                }
            }

            if (!monitoramentoLoginInterval) {
                if (isLoggi) {
                    falarCidade("Atenção: Sessão da Loggi desconectada. Clique em Entrar com o Google no Chrome");
                } else if (isImile) {
                    falarCidade("Atenção: Sessão da iMile desconectada. Faça o login no Chrome");
                } else {
                    falarCidade("Atenção: Sessão da Anjun desconectada. Resolva o não sou robô no Chrome");
                }
                emitirBeepErro();
            }
            mostrarOverlayAguardandoLogin(isLoggi ? "Sessão desconectada. Clique em <strong>'Entrar com o Google'</strong> no Chrome para continuar." : (isImile ? "Sessão da iMile desconectada. Faça o <strong>login na iMile</strong> no Chrome para continuar." : "Sessão desconectada. Resolva o <strong>'Não sou robô'</strong> no Chrome para continuar."), platAlvo);
            iniciarMonitoramentoLogin(platAlvo);
            return;
        }

        // Proteção contra perda de pacote em caso de oscilação momentânea de internet:
        // Mantém o pacote na fila e realiza 1 retentativa automática extra antes de descartar
        const ehOscilacaoRede = msgErro.includes("internet lenta") || msgErro.includes("oscilação") || msgErro.includes("timed out") || msgErro.includes("timeout") || msgErro.includes("urlopen error") || msgErro.includes("connection reset");
        if (ehOscilacaoRede && filaBipes[0]) {
            const itemRede = filaBipes[0];
            itemRede.tentativasRede = (itemRede.tentativasRede || 0) + 1;
            if (itemRede.tentativasRede <= 1) {
                statusPanel.className = 'status-container awaiting';
                statusLabel.innerText = "RECONECTANDO INTERNET...";
                subStatusLabel.innerText = `Oscilação de rede detectada. Retentando pacote ${codigo} automaticamente...`;
                await new Promise(r => setTimeout(r, 650));
                processarProximoDaFila();
                return;
            }
        }

        statusPanel.className = 'status-container error';
        statusLabel.innerText = ehOscilacaoRede ? "FALHA DE INTERNET" : "ERRO";
        subStatusLabel.innerText = `${erro.message}${textoFila}`;
        
        emitirBeepErro();
        
        let falhaFalada = erro.message || "Falha na triagem";
        if (ehOscilacaoRede) {
            falhaFalada = "Atenção: Falha de internet. Bipe o pacote novamente";
        } else if (falhaFalada.toLowerCase().includes("o pacote não existe")) {
            falhaFalada = "Pacote não existe";
        } else if (falhaFalada.startsWith("Alerta Anjun: ")) {
            falhaFalada = falhaFalada.replace("Alerta Anjun: ", "");
        } else if (falhaFalada.startsWith("Alerta iMile: ")) {
            falhaFalada = falhaFalada.replace("Alerta iMile: ", "");
        } else if (falhaFalada.startsWith("Alerta Loggi: ")) {
            falhaFalada = falhaFalada.replace("Alerta Loggi: ", "");
        }
        falarCidade(falhaFalada);
        
        adicionarAoHistorico(codigo, "---", "---", `FALHA: ${erro.message}`, "badge-err");
        
        if (motorista) {
            atribuicaoFeedback.innerText = `Erro: ${erro.message}`;
            atribuicaoFeedback.style.color = "#f87171";
        }
    }

    // Remove o item processado da fila e atualiza o armazenamento local persistente
    filaBipes.shift();
    salvarFilaNoLocalStorage();

    // Executa o próximo item da fila IMEDIATAMENTE (sem delay artificial e sem requisições concorrentes)
    if (filaBipes.length > 0) {
        processarProximoDaFila();
    } else {
        processandoFila = false;
        carregarLotesFinalizados();
        atualizarDivergenciasPendentes();
    }
}

// Interceptador Global de Leitor de Código de Barras (Zero perda do 1º dígito mesmo se o foco estiver fora da caixa)
document.addEventListener('keydown', (e) => {
    if (sistemaTravado || aguardandoLoginAtivo || !input) return;
    if (settingsModal && !settingsModal.classList.contains('hidden')) return;
    const overlayCustom = document.getElementById('custom-alert-overlay');
    if (overlayCustom && overlayCustom.style.display === 'flex') return;

    const elAtivo = document.activeElement;
    if (elAtivo === input) return; // Já está no campo de bipe normal

    const tagAtiva = elAtivo ? (elAtivo.tagName || '').toUpperCase() : '';
    const ehCampoEditavel = (tagAtiva === 'INPUT' || tagAtiva === 'TEXTAREA' || tagAtiva === 'SELECT' || (elAtivo && elAtivo.isContentEditable));
    if (ehCampoEditavel) return;

    if (e.key && e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        input.focus();
        input.value += e.key;
    } else if (e.key === 'Enter' && input.value.trim().length > 0) {
        e.preventDefault();
        input.focus();
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    }
});

// Evento de envio do leitor físico (Enter)
input.addEventListener('keydown', (e) => {
    if (sistemaTravado) {
        e.preventDefault();
        input.value = '';
        return;
    }
    if (e.key === 'Enter') {
        const codigo = input.value.trim();
        input.value = ''; // Limpa instantaneamente para próxima leitura do operador
        
        if (!codigo) return;

        // Se estiver visualizando outra data, volta para "Hoje" ao bipar
        const filterDateStart = document.getElementById('filter-date-start');
        const filterDateEnd = document.getElementById('filter-date-end');
        const hojeLocal = obterDataHojeLocal();
        if ((filterDateStart && filterDateStart.value !== hojeLocal) || (filterDateEnd && filterDateEnd.value !== hojeLocal)) {
            if (filterDateStart) filterDateStart.value = hojeLocal;
            if (filterDateEnd) filterDateEnd.value = hojeLocal;
            atualizarFechamentoData(hojeLocal, hojeLocal);
        }

        const platSelecionada = platformSelector.value;
        if (!platSelecionada) {
            alert("Nenhuma plataforma está selecionada.");
            return;
        }

        let motoristaLote = driverSelect.value || null;
        let cidadesParaEnviar = [];
        if (platSelecionada === 'loggi') {
            cidadesParaEnviar = [...cidadesLoggiSelecionadas];
            motoristaLote = cidadesParaEnviar.length > 0 ? cidadesParaEnviar[0] : null;
        }

        // Adiciona o bipe à fila de processamento e salva no localStorage
        filaBipes.push({ 
            codigo: codigo, 
            plataforma: platSelecionada, 
            motorista: motoristaLote,
            cidades_selecionadas: cidadesParaEnviar,
            pacote_solto: (platSelecionada === 'imile' && pacoteSoltoAtivo)
        });
        salvarFilaNoLocalStorage();

        // Inicia o processamento caso a fila esteja ociosa e não esteja aguardando login
        if (!processandoFila && !aguardandoLoginAtivo) {
            processarProximoDaFila();
        } else if (aguardandoLoginAtivo) {
            const filaTotal = filaBipes.length;
            subStatusLabel.innerText = `Sessão desconectada. [Fila: ${filaTotal} pacote(s) aguardando login]`;
        } else {
            // Atualiza feedback da fila imediatamente
            const filaRestante = filaBipes.length - 1;
            subStatusLabel.innerText = `Processando anterior... [Fila: ${filaRestante} pendente(s)]`;
        }
    }
});



// Preenche o seletor de motoristas/cidades na tela de atribuição
function popularDropdownCidadesLoggi() {
    if (!loggiCityAddSelect) return;
    const cidadesOrdenadas = Array.from(new Set(todasCidades)).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
    const cidadesDisponiveis = cidadesOrdenadas.filter(c => !cidadesLoggiSelecionadas.includes(c));
    
    let placeholder = "+ Adicionar Cidade Secundária ao Grupo...";
    if (cidadesLoggiSelecionadas.length === 0) {
        placeholder = "⭐ Selecione a Cidade Principal do Grupo...";
    }
    
    loggiCityAddSelect.innerHTML = `<option value="">${placeholder}</option>` +
        cidadesDisponiveis.map(c => `<option value="${c}">${c}</option>`).join('');
}

function renderizarBadgesCidadesLoggi() {
    if (!loggiSelectedCitiesTags) return;
    
    if (cidadesLoggiSelecionadas.length === 0) {
        loggiSelectedCitiesTags.innerHTML = `<span style="color: #64748b; font-style: italic; font-size: 0.78rem; padding: 4px;">👆 Clique nas cidades da lista lateral para montar o grupo</span>`;
        if (driverSelect) driverSelect.value = "";
        return;
    }
    
    // Atualiza driverSelect.value com a primeira cidade (cidade principal do grupo) para compatibilidade
    if (driverSelect) {
        let optExiste = false;
        for (let opt of driverSelect.options) {
            if (opt.value === cidadesLoggiSelecionadas[0]) {
                optExiste = true;
                break;
            }
        }
        if (!optExiste) {
            const novaOpt = document.createElement('option');
            novaOpt.value = cidadesLoggiSelecionadas[0];
            novaOpt.text = cidadesLoggiSelecionadas[0];
            driverSelect.appendChild(novaOpt);
        }
        driverSelect.value = cidadesLoggiSelecionadas[0];
    }
    
    loggiSelectedCitiesTags.innerHTML = cidadesLoggiSelecionadas.map((cidade, idx) => {
        if (idx === 0) {
            return `
                <div class="loggi-city-pill primary" title="1ª Cidade Principal (Nome do Grupo na Loggi)">
                    <span>⭐ 1ª ${cidade} (Principal)</span>
                    <span class="pill-remove" onclick="removerCidadeLoggi(0)" title="Remover cidade do grupo">✕</span>
                </div>
            `;
        } else {
            return `
                <div class="loggi-city-pill" title="${idx + 1}ª Cidade autorizada neste grupo">
                    <span>✓ ${idx + 1}ª ${cidade}</span>
                    <span class="pill-remove" onclick="removerCidadeLoggi(${idx})" title="Remover cidade do grupo">✕</span>
                </div>
            `;
        }
    }).join('');
}

async function finalizarLoteLoggiAutomatico(cidadeAnterior) {
    if (!cidadeAnterior) return;
    try {
        const res = await fetch(`${API_URL}/atribuicao/finalizar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                motorista: cidadeAnterior, 
                plataforma: 'loggi',
                apenas_se_tiver_pacotes: true 
            })
        });
        const data = await res.json();
        if (res.ok && data.quantidade > 0) {
            carregarLotesFinalizados();
            if (atribuicaoFeedback) {
                atribuicaoFeedback.innerText = `✓ Lote finalizado (${data.quantidade} pct)`;
                atribuicaoFeedback.style.color = "#34d399";
            }
        }
    } catch (err) {
        console.warn("[Loggi] Falha ao auto-finalizar lote anterior:", err);
    }
}

window.removerCidadeLoggi = async function(index) {
    if (index >= 0 && index < cidadesLoggiSelecionadas.length) {
        const cidRemovida = cidadesLoggiSelecionadas[index];
        const eraPrincipal = (index === 0);
        cidadesLoggiSelecionadas.splice(index, 1);
        salvarCidadesLoggiLocalStorage();
        if (eraPrincipal && cidRemovida) {
            await finalizarLoteLoggiAutomatico(cidRemovida);
        }
        fetch(`${API_URL}/loggi/definir-grupo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                modo: modoGrupoLoggi,
                cidade_principal: cidadesLoggiSelecionadas[0] || null,
                reset: eraPrincipal
            })
        }).catch(() => {});
        popularDropdownCidadesLoggi();
        renderizarBadgesCidadesLoggi();
        atualizarCidadesDoMotoristaSelecionado();
        atualizarContagemAoMudarMotorista();
        if (input) input.focus();
    }
};

function salvarCidadesLoggiLocalStorage() {
    try {
        localStorage.setItem('loggi_cidades_selecionadas', JSON.stringify(cidadesLoggiSelecionadas));
    } catch (e) {}
}

function carregarCidadesLoggiLocalStorage() {
    try {
        const salvo = localStorage.getItem('loggi_cidades_selecionadas');
        if (salvo) {
            cidadesLoggiSelecionadas = JSON.parse(salvo);
            if (!Array.isArray(cidadesLoggiSelecionadas)) cidadesLoggiSelecionadas = [];
        }
    } catch (e) {
        cidadesLoggiSelecionadas = [];
    }
}

// --- SISTEMA DE GRUPOS LOGGI (NOVO E EXISTENTE) ---
async function carregarGruposLoggiAbertos() {
    if (!loggiGrupoExistenteSelect) return;
    try {
        loggiGrupoExistenteSelect.innerHTML = '<option value="">Carregando grupos abertos...</option>';
        const res = await fetch(`${API_URL}/loggi/grupos?_=${Date.now()}`);
        if (!res.ok) throw new Error("Erro ao buscar grupos");
        const data = await res.json();
        gruposLoggiCarregados = data.grupos || [];
        renderizarSelectGruposLoggi();
        
        if (data.grupo_ativo && data.grupo_ativo.licensePlate) {
            atualizarBadgeGrupoLoggi(data.grupo_ativo);
        }
    } catch (e) {
        console.warn("Falha ao carregar grupos da Loggi:", e);
        if (loggiGrupoExistenteSelect) {
            loggiGrupoExistenteSelect.innerHTML = '<option value="">Falha ao listar grupos (verifique login)</option>';
        }
    }
}

function renderizarSelectGruposLoggi(filtro = '') {
    if (!loggiGrupoExistenteSelect) return;
    const filtroNorm = (filtro || '').toLowerCase().trim();
    const filtrados = gruposLoggiCarregados.filter(g => {
        if (!filtroNorm) return true;
        const tag = (g.tag_display || '').toLowerCase();
        const placa = (g.licensePlate || '').toLowerCase();
        return tag.includes(filtroNorm) || placa.includes(filtroNorm);
    });

    if (filtrados.length === 0) {
        loggiGrupoExistenteSelect.innerHTML = '<option value="">Nenhum grupo encontrado</option>';
    } else {
        loggiGrupoExistenteSelect.innerHTML = '<option value="">-- Selecione o Grupo Aberto --</option>' +
            filtrados.map(g => {
                const rotulo = `${g.tag_display} (${g.licensePlate}) - ${g.quantity || 0} pcs`;
                return `<option value="${g.licensePlate}">${rotulo}</option>`;
            }).join('');
    }
    renderizarListaAbertaSidebar();
}

async function consultarGrupoLoggiAtivo() {
    try {
        const res = await fetch(`${API_URL}/loggi/grupo-ativo?_=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            if (data.grupo_ativo && (data.grupo_ativo.licensePlate || data.grupo_ativo.cidade)) {
                atualizarBadgeGrupoLoggi(data.grupo_ativo);
            }
        }
    } catch (e) {}
}

function atualizarBadgeGrupoLoggi(grupo) {
    const activeNameEl = document.getElementById('active-driver-name-display');
    if (grupo && (grupo.licensePlate || (grupo.tags && grupo.tags.length > 0) || grupo.cidade)) {
        const tag = (grupo.tags && grupo.tags.length > 0) ? grupo.tags.join(', ') : (grupo.cidade || grupo.licensePlate);
        const placa = grupo.licensePlate ? ` [Placa: ${grupo.licensePlate}]` : '';
        if (badgeGrupoLoggiTexto) badgeGrupoLoggiTexto.innerText = `${tag}${placa}`;
        if (activeNameEl) activeNameEl.innerText = `${tag}${placa}`;
    } else {
        if (badgeGrupoLoggiTexto) badgeGrupoLoggiTexto.innerText = '';
        if (activeNameEl) {
            const cid = (cidadesLoggiSelecionadas && cidadesLoggiSelecionadas[0]) || '';
            activeNameEl.innerText = cid ? `${cid} (Novo Grupo)` : 'Apenas Entrada (Sem Atribuição)';
        }
    }
    if (badgeGrupoLoggiAtivo) badgeGrupoLoggiAtivo.style.display = 'none';
}

// Alternar modo Novo Grupo vs Grupo Existente
if (tabLoggiNovo) {
    tabLoggiNovo.addEventListener('click', async () => {
        modoGrupoLoggi = 'novo';
        tabLoggiNovo.style.background = '#0284c7';
        tabLoggiNovo.style.color = '#fff';
        if (tabLoggiExistente) {
            tabLoggiExistente.style.background = 'transparent';
            tabLoggiExistente.style.color = '#94a3b8';
        }
        if (panelLoggiNovo) panelLoggiNovo.style.display = 'flex';
        if (panelLoggiExistente) panelLoggiExistente.style.display = 'none';
        renderizarListaAbertaSidebar();
        
        try {
            await fetch(`${API_URL}/loggi/definir-grupo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ modo: 'novo', cidade: cidadesLoggiSelecionadas[0] || null })
            });
        } catch (e) {}
        if (input) input.focus();
    });
}

if (tabLoggiExistente) {
    tabLoggiExistente.addEventListener('click', async () => {
        modoGrupoLoggi = 'existente';
        tabLoggiExistente.style.background = '#0284c7';
        tabLoggiExistente.style.color = '#fff';
        if (tabLoggiNovo) {
            tabLoggiNovo.style.background = 'transparent';
            tabLoggiNovo.style.color = '#94a3b8';
        }
        if (panelLoggiNovo) panelLoggiNovo.style.display = 'none';
        if (panelLoggiExistente) panelLoggiExistente.style.display = 'flex';
        renderizarListaAbertaSidebar();
        
        carregarGruposLoggiAbertos();
        if (input) input.focus();
    });
}

if (btnAtualizarGruposLoggi) {
    btnAtualizarGruposLoggi.addEventListener('click', () => {
        carregarGruposLoggiAbertos();
        if (input) input.focus();
    });
}

if (filtroBuscaGrupoLoggi) {
    filtroBuscaGrupoLoggi.addEventListener('input', (e) => {
        renderizarSelectGruposLoggi(e.target.value);
    });
}

if (loggiGrupoExistenteSelect) {
    loggiGrupoExistenteSelect.addEventListener('change', async () => {
        loggiGrupoExistenteSelect.blur();
        const placa = loggiGrupoExistenteSelect.value;
        if (!placa) return;
        const grupo = gruposLoggiCarregados.find(g => g.licensePlate === placa);
        if (grupo) {
            try {
                const cidAnterior = (cidadesLoggiSelecionadas && cidadesLoggiSelecionadas.length > 0) ? cidadesLoggiSelecionadas[0] : null;
                if (cidAnterior) {
                    await finalizarLoteLoggiAutomatico(cidAnterior);
                    cidadesLoggiSelecionadas = [];
                    salvarCidadesLoggiLocalStorage();
                    popularDropdownCidadesLoggi();
                    renderizarBadgesCidadesLoggi();
                }
                const res = await fetch(`${API_URL}/loggi/definir-grupo`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        modo: 'existente',
                        licensePlate: grupo.licensePlate,
                        tags: grupo.tags,
                        cidade: grupo.tag_display
                    })
                });
                if (res.ok) {
                    atualizarBadgeGrupoLoggi(grupo);
                    atribuicaoCounter.innerText = `${grupo.quantity || 0} PACOTES BIPADOS`;
                    atribuicaoFeedback.innerText = `Grupo ${grupo.tag_display} ativado! Bipe os pacotes.`;
                    atribuicaoFeedback.style.color = "#4ade80";
                    renderizarListaAbertaSidebar();
                }
            } catch (e) {
                console.error("Erro ao ativar grupo existente:", e);
            }
        }
        if (input) input.focus();
    });
}

if (btnCriarGrupoAgora) {
    btnCriarGrupoAgora.addEventListener('click', async () => {
        btnCriarGrupoAgora.blur();
        const cid = (cidadesLoggiSelecionadas && cidadesLoggiSelecionadas[0] ? cidadesLoggiSelecionadas[0].trim() : '') || (loggiCityAddSelect ? loggiCityAddSelect.value.trim() : '');
        const cidFinal = cid || await customPrompt("Criar Grupo Loggi", "Digite o nome da cidade para criar o grupo:", "");
        if (!cidFinal) {
            setTimeout(() => { if (input) input.focus(); }, 50);
            return;
        }
        
        btnCriarGrupoAgora.disabled = true;
        btnCriarGrupoAgora.innerText = "Criando...";
        try {
            const res = await fetch(`${API_URL}/loggi/criar-grupo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cidade: cidFinal, forcar: true })
            });
            const data = await res.json();
            if (res.ok) {
                if (!cidadesLoggiSelecionadas.includes(cidFinal)) {
                    cidadesLoggiSelecionadas.unshift(cidFinal);
                    salvarCidadesLoggiLocalStorage();
                    popularDropdownCidadesLoggi();
                    renderizarBadgesCidadesLoggi();
                    renderizarListaAbertaSidebar();
                }
                atualizarBadgeGrupoLoggi({
                    licensePlate: data.licensePlate,
                    tags: [data.tag],
                    cidade: cidFinal
                });
                atribuicaoCounter.innerText = "0 PACOTES BIPADOS";
                atribuicaoFeedback.innerText = `✅ Grupo ativo: ${data.tag} [Placa: ${data.licensePlate}]! Pronto para bipar.`;
                atribuicaoFeedback.style.color = "#4ade80";
                try { playBeep('sucesso'); } catch (e) {}
                carregarGruposLoggiAbertos();
            } else {
                await customAlert("Erro ao criar grupo na Loggi", data.mensagem || "Erro");
            }
        } catch (e) {
            await customAlert("Erro de conexão", "Erro de conexão ao criar grupo: " + e.message);
        } finally {
            btnCriarGrupoAgora.disabled = false;
            btnCriarGrupoAgora.innerText = "+ Criar Agora";
            btnCriarGrupoAgora.blur();
            if (input) input.focus();
            setTimeout(() => { if (input) input.focus(); }, 60);
        }
    });
}

// Configura listeners do seletor de cidades da Loggi
if (loggiCityAddSelect) {
    loggiCityAddSelect.addEventListener('change', () => {
        const val = loggiCityAddSelect.value.trim();
        loggiCityAddSelect.blur(); // Libera o foco do combobox imediatamente
        
        if (val && !cidadesLoggiSelecionadas.includes(val)) {
            cidadesLoggiSelecionadas.push(val);
            salvarCidadesLoggiLocalStorage();
            
            fetch(`${API_URL}/loggi/definir-grupo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    modo: modoGrupoLoggi, 
                    cidade_principal: cidadesLoggiSelecionadas[0],
                    reset: false 
                })
            }).catch(() => {});
        }
        
        setTimeout(() => {
            popularDropdownCidadesLoggi();
            renderizarBadgesCidadesLoggi();
            atualizarCidadesDoMotoristaSelecionado();
            atualizarContagemAoMudarMotorista();
            renderizarListaAbertaSidebar();
            if (input) input.focus();
        }, 80);
    });
}

if (btnLimparCidadesLoggi) {
    btnLimparCidadesLoggi.addEventListener('click', async () => {
        if (cidadesLoggiSelecionadas.length > 0) {
            const cidAnterior = cidadesLoggiSelecionadas[0];
            cidadesLoggiSelecionadas = [];
            salvarCidadesLoggiLocalStorage();
            popularDropdownCidadesLoggi();
            renderizarBadgesCidadesLoggi();
            atualizarCidadesDoMotoristaSelecionado();
            atualizarContagemAoMudarMotorista();
            renderizarListaAbertaSidebar();
            
            if (cidAnterior) {
                await finalizarLoteLoggiAutomatico(cidAnterior);
            }
            fetch(`${API_URL}/loggi/definir-grupo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ modo: 'novo', cidade: null, reset: true })
            }).catch(() => {});
        }
        if (input) input.focus();
    });
}

// --- LISTA SEMPRE ABERTA NA COLUNA ESQUERDA (MOTORISTAS / CIDADES LOGGI / GRUPOS LOGGI) ---
const sidebarSearchInput = document.getElementById('sidebar-search-input');
function normalizarBuscaSidebar(str) {
    return String(str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}
if (sidebarSearchInput) {
    sidebarSearchInput.addEventListener('input', () => {
        renderizarListaAbertaSidebar();
    });
    sidebarSearchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            sidebarSearchInput.value = '';
            renderizarListaAbertaSidebar();
            if (input) input.focus();
        }
    });
}

function renderizarListaAbertaSidebar() {
    const listContainer = document.getElementById('sidebar-open-list');
    const titleEl = document.getElementById('sidebar-left-title');
    const loggiTabs = document.getElementById('sidebar-loggi-tabs');
    if (!listContainer) return;

    const platSelecionada = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    const termoBusca = normalizarBuscaSidebar(sidebarSearchInput ? sidebarSearchInput.value : "");

    if (platSelecionada === 'loggi') {
        if (loggiTabs) loggiTabs.style.display = 'flex';
        if (modoGrupoLoggi === 'existente') {
            if (titleEl) titleEl.innerText = "GRUPOS ABERTOS (LOGGI):";
            if (btnAtualizarGruposLoggi) btnAtualizarGruposLoggi.style.display = 'inline-flex';
            if (sidebarSearchInput) sidebarSearchInput.placeholder = "🔍 Filtrar grupo aberto...";

            const filtrados = (gruposLoggiCarregados || []).filter(g => {
                if (!termoBusca) return true;
                const tag = normalizarBuscaSidebar(g.tag_display || '');
                const placa = normalizarBuscaSidebar(g.licensePlate || '');
                return tag.includes(termoBusca) || placa.includes(termoBusca);
            });

            if (filtrados.length === 0) {
                listContainer.innerHTML = `<div style="padding: 14px 10px; color: #64748b; font-size: 0.76rem; text-align: center;">Nenhum grupo aberto encontrado.</div>`;
                return;
            }

            const placaAtiva = loggiGrupoExistenteSelect ? loggiGrupoExistenteSelect.value : "";
            listContainer.innerHTML = filtrados.map(g => {
                const isSel = (placaAtiva && placaAtiva === g.licensePlate);
                const escapedPlaca = (g.licensePlate || '').replace(/'/g, "\\'");
                return `
                    <div class="sidebar-list-item ${isSel ? 'active' : ''}" onclick="selecionarGrupoExistenteSidebar('${escapedPlaca}')">
                        <span style="overflow: hidden; text-overflow: ellipsis;">📂 ${g.tag_display || g.licensePlate}</span>
                        <span style="font-size: 0.68rem; background: rgba(0,0,0,0.3); padding: 1px 6px; border-radius: 4px; flex-shrink: 0;">${g.quantity || 0} pcs</span>
                    </div>
                `;
            }).join('');
        } else {
            if (titleEl) titleEl.innerText = "CIDADES (LOGGI):";
            if (btnAtualizarGruposLoggi) btnAtualizarGruposLoggi.style.display = 'none';
            if (sidebarSearchInput) sidebarSearchInput.placeholder = "🔍 Buscar cidade...";

            const cidadesOrdenadas = Array.from(new Set(todasCidades)).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            const filtradas = cidadesOrdenadas.filter(c => !termoBusca || normalizarBuscaSidebar(c).includes(termoBusca));

            if (filtradas.length === 0) {
                listContainer.innerHTML = `<div style="padding: 14px 10px; color: #64748b; font-size: 0.76rem; text-align: center;">Nenhuma cidade encontrada.</div>`;
                return;
            }

            listContainer.innerHTML = filtradas.map(c => {
                const idx = cidadesLoggiSelecionadas.indexOf(c);
                const escapedCid = c.replace(/'/g, "\\'");
                if (idx === 0) {
                    return `
                        <div class="sidebar-list-item active" onclick="alternarCidadeLoggiSidebar('${escapedCid}')" title="1ª Cidade Principal. Clique para remover do grupo">
                            <span style="overflow: hidden; text-overflow: ellipsis;">⭐ ${c}</span>
                            <span style="font-size: 0.65rem; background: rgba(0,0,0,0.25); padding: 1px 5px; border-radius: 4px; flex-shrink: 0;">1ª Principal</span>
                        </div>
                    `;
                } else if (idx > 0) {
                    return `
                        <div class="sidebar-list-item active-secondary" onclick="alternarCidadeLoggiSidebar('${escapedCid}')" title="${idx + 1}ª Cidade Secundária. Clique para remover do grupo">
                            <span style="overflow: hidden; text-overflow: ellipsis;">✓ ${c}</span>
                            <span style="font-size: 0.65rem; flex-shrink: 0;">${idx + 1}ª</span>
                        </div>
                    `;
                } else {
                    return `
                        <div class="sidebar-list-item" onclick="alternarCidadeLoggiSidebar('${escapedCid}')" title="Clique para adicionar ao grupo">
                            <span style="overflow: hidden; text-overflow: ellipsis;">${c}</span>
                        </div>
                    `;
                }
            }).join('');
        }
    } else {
        if (loggiTabs) loggiTabs.style.display = 'none';
        if (btnAtualizarGruposLoggi) btnAtualizarGruposLoggi.style.display = 'none';
        if (titleEl) titleEl.innerText = "MOTORISTA ATIVO:";
        if (sidebarSearchInput) sidebarSearchInput.placeholder = "🔍 Buscar motorista...";

        const valorAtual = driverSelect ? driverSelect.value : "";
        const motoristasList = Array.isArray(todosMotoristas)
            ? todosMotoristas.map(m => m.motorista)
            : Object.values(todosMotoristas);
        const motoristasSet = new Set(motoristasList.map(m => (m || '').trim()).filter(m => m && m !== "Sem Motorista"));
        const motoristasOrdenados = Array.from(motoristasSet).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
        const filtrados = motoristasOrdenados.filter(m => !termoBusca || normalizarBuscaSidebar(m).includes(termoBusca));

        let html = `
            <div class="sidebar-list-item ${valorAtual === '' ? 'active' : ''}" onclick="selecionarMotoristaSidebar('')">
                <span style="overflow: hidden; text-overflow: ellipsis;">Apenas Entrada (Sem Atribuição)</span>
            </div>
        `;
        html += filtrados.map(m => {
            const isSel = (valorAtual === m);
            const escapedMot = m.replace(/'/g, "\\'");
            return `
                <div class="sidebar-list-item ${isSel ? 'active' : ''}" onclick="selecionarMotoristaSidebar('${escapedMot}')">
                    <span style="overflow: hidden; text-overflow: ellipsis;">${m}</span>
                </div>
            `;
        }).join('');

        listContainer.innerHTML = html;
    }
}

window.selecionarMotoristaSidebar = function(motoristaNome) {
    if (driverSelect) {
        driverSelect.value = motoristaNome;
    }
    const driverCitiesSection = document.getElementById('driver-cities-section');
    const containerLoggiCities = document.getElementById('container-loggi-cities');
    const platSelecionada = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    if (platSelecionada !== 'loggi') {
        if (driverCitiesSection) driverCitiesSection.style.display = 'flex';
        if (containerLoggiCities) containerLoggiCities.style.display = 'none';
    }
    renderizarListaAbertaSidebar();
    atualizarContagemAoMudarMotorista();
    if (input) input.focus();
};

window.alternarCidadeLoggiSidebar = async function(cidadeNome) {
    if (!cidadeNome) return;
    
    const idx = cidadesLoggiSelecionadas.indexOf(cidadeNome);
    if (idx >= 0) {
        cidadesLoggiSelecionadas.splice(idx, 1);
    } else {
        cidadesLoggiSelecionadas.push(cidadeNome);
    }
    salvarCidadesLoggiLocalStorage();

    const cidPrincipal = cidadesLoggiSelecionadas[0] || null;
    const activeNameEl = document.getElementById('active-driver-name-display');
    if (cidPrincipal) {
        if (activeNameEl) activeNameEl.innerText = `${cidPrincipal} (Carregando grupo...)`;
    } else {
        if (activeNameEl) activeNameEl.innerText = 'Apenas Entrada (Sem Atribuição)';
        if (atribuicaoCounter) atribuicaoCounter.innerText = '0 pacotes bipados';
        if (atribuicaoFeedback) {
            atribuicaoFeedback.innerText = 'Aguardando início...';
            atribuicaoFeedback.style.color = '#34d399';
        }
    }

    try {
        const res = await fetch(`${API_URL}/loggi/definir-grupo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                modo: 'novo',
                cidade: cidPrincipal,
                cidade_principal: cidPrincipal,
                reset: cidadesLoggiSelecionadas.length === 0
            })
        });
        if (res.ok) {
            const data = await res.json();
            const grp = data.grupo_ativo;
            if (grp && grp.licensePlate) {
                atualizarBadgeGrupoLoggi(grp);
                if (atribuicaoCounter) atribuicaoCounter.innerText = `${grp.quantity || 0} PACOTES BIPADOS`;
                if (atribuicaoFeedback) {
                    atribuicaoFeedback.innerText = `Grupo ${grp.tags && grp.tags[0] ? grp.tags[0] : grp.licensePlate} pronto!`;
                    atribuicaoFeedback.style.color = "#4ade80";
                }
            } else if (cidPrincipal) {
                const hojeStr = new Date();
                const diaMesStr = `${String(hojeStr.getDate()).padStart(2, '0')}-${String(hojeStr.getMonth() + 1).padStart(2, '0')}`;
                if (activeNameEl) activeNameEl.innerText = `${cidPrincipal} ${diaMesStr} (Novo Grupo)`;
                if (atribuicaoCounter) atribuicaoCounter.innerText = `0 PACOTES BIPADOS`;
                if (atribuicaoFeedback) {
                    atribuicaoFeedback.innerText = `Pronto para bipar!`;
                    atribuicaoFeedback.style.color = "#38bdf8";
                }
            }
        }
    } catch (e) {
        console.warn("Erro ao sincronizar grupo Loggi:", e);
    }

    popularDropdownCidadesLoggi();
    renderizarBadgesCidadesLoggi();
    atualizarCidadesDoMotoristaSelecionado();
    atualizarContagemAoMudarMotorista();
    renderizarListaAbertaSidebar();
    if (input) input.focus();
};

window.selecionarGrupoExistenteSidebar = function(placa) {
    if (loggiGrupoExistenteSelect) {
        loggiGrupoExistenteSelect.value = placa;
        loggiGrupoExistenteSelect.dispatchEvent(new Event('change'));
    }
    if (input) input.focus();
};

// Preenche o dropdown de motoristas na tela de atribuição
function atualizarSeletorMotoristas() {
    const platSelecionada = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    const driverCitiesSection = document.getElementById('driver-cities-section');
    const tituloCardMot = document.getElementById('titulo-card-motorista-atual');
    
    if (btnFinalizarLote) {
        btnFinalizarLote.style.display = (platSelecionada === 'anjun' || platSelecionada === 'loggi') ? 'flex' : 'none';
    }

    if (platSelecionada === 'loggi') {
        if (containerDriverStandard) containerDriverStandard.style.display = 'none';
        if (containerLoggiCities) containerLoggiCities.style.display = 'flex';
        if (driverCitiesSection) driverCitiesSection.style.display = 'none';
        if (tituloCardMot) tituloCardMot.innerHTML = '<span>🚚</span> GRUPO ATUAL (LOGGI)';
        if (driverCitiesLabel) driverCitiesLabel.innerText = "CIDADES DO GRUPO (LOGGI):";
        
        carregarCidadesLoggiLocalStorage();
        popularDropdownCidadesLoggi();
        renderizarBadgesCidadesLoggi();
        carregarGruposLoggiAbertos();
        consultarGrupoLoggiAtivo();
    } else {
        if (containerDriverStandard) containerDriverStandard.style.display = 'none';
        if (containerLoggiCities) containerLoggiCities.style.display = 'none';
        if (driverCitiesSection) driverCitiesSection.style.display = 'flex';
        if (tituloCardMot) tituloCardMot.innerHTML = '<span>🚚</span> MOTORISTA ATUAL';
        if (driverCitiesLabel) driverCitiesLabel.innerText = "CIDADES VINCULADAS AO MOTORISTA:";
        
        if (driverSelect) {
            const valorAnterior = driverSelect.value || "";
            const motoristasList = Array.isArray(todosMotoristas) 
                ? todosMotoristas.map(m => m.motorista) 
                : Object.values(todosMotoristas);
            const motoristasSet = new Set(motoristasList.map(m => (m || '').trim()).filter(m => m && m !== "Sem Motorista"));
            const motoristasOrdenados = Array.from(motoristasSet).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            driverSelect.innerHTML = '<option value="">Apenas Entrada (Sem Atribuição)</option>' + 
                motoristasOrdenados.map(m => `<option value="${m}">${m}</option>`).join('');
            if (valorAnterior && motoristasOrdenados.includes(valorAnterior)) {
                driverSelect.value = valorAnterior;
            }
        }
    }
        
    renderizarListaAbertaSidebar();
    renderizarCardsKpiEmpresas();
    atualizarCidadesDoMotoristaSelecionado();
}

// Sincroniza o status do lote ativo (útil se recarregar a página)
async function sincronizarStatusLoteAtivo() {
    try {
        const res = await fetch(`${API_URL}/atribuicao/status?_=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            if (data.motorista) {
                driverSelect.value = data.motorista;
                atribuicaoCounter.innerText = `${data.contagem} PACOTES BIPADOS`;
                atribuicaoFeedback.innerText = "Lote ativo em execução...";
                renderizarListaAbertaSidebar();
                atualizarCidadesDoMotoristaSelecionado();
            }
        }
    } catch (e) {
        console.error("Erro ao sincronizar status do lote ativo:", e);
    }
}

// Finalizar Lote de Atribuição
if (btnFinalizarLote) {
    btnFinalizarLote.addEventListener('click', async () => {
        const platSelecionada = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
        let motorista = driverSelect ? driverSelect.value : "";
        
        if (platSelecionada === 'loggi') {
            const tagAtiva = badgeGrupoLoggiTexto ? badgeGrupoLoggiTexto.innerText.replace('🟢 Grupo Ativo:', '').trim() : '';
            motorista = cidadesLoggiSelecionadas[0] || tagAtiva || "Loggi";
            if (!confirm(`Confirmar encerramento e finalização do lote/grupo da Loggi (${motorista})?`)) {
                if (input) input.focus();
                return;
            }
        } else {
            if (!motorista) {
                alert("Selecione um motorista primeiro.");
                if (input) input.focus();
                return;
            }
            if (!confirm(`Confirmar encerramento e emissão da folha de entrega para o motorista "${motorista}"?`)) {
                if (input) input.focus();
                return;
            }
        }

        btnFinalizarLote.disabled = true;
        btnFinalizarLote.innerText = "FINALIZANDO...";

        try {
            const res = await fetch(`${API_URL}/atribuicao/finalizar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motorista: motorista, plataforma: platSelecionada })
            });
            const data = await res.json();

            if (res.ok) {
                atribuicaoCounter.innerText = "0 pacotes bipados";
                atribuicaoFeedback.innerText = "Pronto para iniciar";
                if (platSelecionada === 'loggi') {
                    if (badgeGrupoLoggiAtivo) badgeGrupoLoggiAtivo.style.display = 'none';
                    if (badgeGrupoLoggiTexto) badgeGrupoLoggiTexto.innerText = "🟢 Grupo Ativo: Aguardando bipe...";
                    cidadesLoggiSelecionadas = [];
                    salvarCidadesLoggiLocalStorage();
                    popularDropdownCidadesLoggi();
                    renderizarBadgesCidadesLoggi();
                    renderizarListaAbertaSidebar();
                    carregarGruposLoggiAbertos();
                }
                carregarLotesFinalizados();
                alert(`Lote de "${motorista}" finalizado com sucesso!`);
            } else {
                alert("Erro ao finalizar lote: " + (data.mensagem || "Erro desconhecido"));
            }
        } catch (e) {
            alert("Erro de conexão: " + e.message);
        } finally {
            btnFinalizarLote.disabled = false;
            btnFinalizarLote.innerText = "✓ FINALIZAR LOTE";
            if (input) input.focus();
        }
    });
}

// --- SISTEMA DE LOTES FINALIZADOS ---
const lotesFinalizadosLog = document.getElementById('lotes-finalizados-log');
const filtroMotoristasBipados = document.getElementById('filtro-motoristas-bipados');
let lotesFinalizadosCarregados = [];
let colunaOrdenacaoAtual = 'quantidade';
let ordenacaoAscendente = false; // Começa decrescente (do maior para o menor) por padrão

if (filtroMotoristasBipados) {
    filtroMotoristasBipados.addEventListener('input', () => {
        aplicarOrdenacaoERenderizar();
    });
}

async function carregarLotesFinalizados() {
    if (!lotesFinalizadosLog) return;
    try {
        const res = await fetch(`${API_URL}/atribuicao/lotes-finalizados?_=${Date.now()}`);
        if (res.ok) {
            lotesFinalizadosCarregados = await res.json();
            recalcularContagemEmpresas(null, lotesFinalizadosCarregados);
            aplicarOrdenacaoERenderizar();
        }
    } catch (e) {
        console.error("Erro ao carregar lotes finalizados:", e);
    }
}

function ordenarTabela(campo) {
    if (colunaOrdenacaoAtual === campo) {
        ordenacaoAscendente = !ordenacaoAscendente;
    } else {
        colunaOrdenacaoAtual = campo;
        // Se for quantidade, começa decrescente (false). Se for texto, começa de A-Z (true)
        ordenacaoAscendente = (campo !== 'quantidade');
    }
    aplicarOrdenacaoERenderizar();
}

window.ordenarTabela = ordenarTabela; // Expõe globalmente para o onclick do HTML

function aplicarOrdenacaoERenderizar() {
    if (!lotesFinalizadosCarregados || lotesFinalizadosCarregados.length === 0) {
        renderizarLotesFinalizados([]);
        return;
    }
    
    const termoFiltro = (filtroMotoristasBipados ? filtroMotoristasBipados.value : "").toLowerCase().trim();
    const listaFiltrada = lotesFinalizadosCarregados.filter(item => {
        if (!termoFiltro) return true;
        const m = (item.motorista || '').toLowerCase();
        const c = (item.cidades || '').toLowerCase();
        const p = (item.plataforma || '').toLowerCase();
        return m.includes(termoFiltro) || c.includes(termoFiltro) || p.includes(termoFiltro);
    });

    const listaOrdenada = [...listaFiltrada].sort((a, b) => {
        let valA = a[colunaOrdenacaoAtual];
        let valB = b[colunaOrdenacaoAtual];
        
        if (typeof valA === 'string') {
            valA = valA.toLowerCase();
            valB = valB.toLowerCase();
        }
        
        if (valA < valB) return ordenacaoAscendente ? -1 : 1;
        if (valA > valB) return ordenacaoAscendente ? 1 : -1;
        return 0;
    });
    
    // Atualiza os ícones de cabeçalho
    const colunas = ['motorista', 'cidades', 'plataforma', 'quantidade'];
    colunas.forEach(col => {
        const elemIcon = document.getElementById(`sort-icon-${col}`);
        if (elemIcon) {
            if (col === colunaOrdenacaoAtual) {
                elemIcon.innerText = ordenacaoAscendente ? " ▲" : " ▼";
                elemIcon.style.color = "#38bdf8";
            } else {
                elemIcon.innerText = " ⇅";
                elemIcon.style.color = "#475569";
            }
        }
    });
    
    renderizarLotesFinalizados(listaOrdenada);
}

let motoristasExpandidos = new Set();

function renderizarLotesFinalizados(lista) {
    const platAtual = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    const baseLista = Array.isArray(lotesFinalizadosCarregados) && lotesFinalizadosCarregados.length > 0 ? lotesFinalizadosCarregados : lista;
    const abertosAnjun = baseLista.filter(item => (item.qtd_pendente || 0) > 0);
    const ehAnjun = (platAtual === 'anjun') || abertosAnjun.length > 0;
    
    // Atualiza visibilidade dos botões em lote da Anjun ("✓ Finalizar Todos" e "✕ Cancelar")
    const anjunActionsEl = document.getElementById('anjun-lotes-actions');
    const btnFinalizarTodosEl = document.getElementById('btn-finalizar-todos-anjun');
    if (anjunActionsEl) {
        if (ehAnjun) {
            anjunActionsEl.style.display = 'flex';
            if (btnFinalizarTodosEl) {
                btnFinalizarTodosEl.innerText = abertosAnjun.length > 0
                    ? `✓ Finalizar Todos (${abertosAnjun.length})`
                    : `✓ Finalizar Todos`;
            }
        } else {
            anjunActionsEl.style.display = 'none';
        }
    }

    // Atualiza cabeçalhos da tabela conforme a plataforma
    const thPlat = document.getElementById('th-plataforma');
    const thQtd = document.getElementById('th-quantidade');
    if (thPlat && thQtd) {
        if (ehAnjun) {
            thPlat.innerHTML = `Lote Aberto <span id="sort-icon-plataforma">${colunaOrdenacaoAtual === 'plataforma' ? (ordenacaoAscendente ? " ▲" : " ▼") : " ⇅"}</span>`;
            thPlat.style.width = '145px';
            thQtd.innerHTML = `Total <span id="sort-icon-quantidade">${colunaOrdenacaoAtual === 'quantidade' ? (ordenacaoAscendente ? " ▲" : " ▼") : " ⇅"}</span>`;
            thQtd.style.width = '55px';
        } else {
            thPlat.innerHTML = `Plat <span id="sort-icon-plataforma">${colunaOrdenacaoAtual === 'plataforma' ? (ordenacaoAscendente ? " ▲" : " ▼") : " ⇅"}</span>`;
            thPlat.style.width = '65px';
            thQtd.innerHTML = `Qtd <span id="sort-icon-quantidade">${colunaOrdenacaoAtual === 'quantidade' ? (ordenacaoAscendente ? " ▲" : " ▼") : " ⇅"}</span>`;
            thQtd.style.width = '65px';
        }
    }

    if (lista.length === 0) {
        lotesFinalizadosLog.innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; color: #64748b; padding: 15px; font-size: 0.72rem;">
                    Nenhum pacote bipado hoje.
                </td>
            </tr>
        `;
        return;
    }
    lotesFinalizadosLog.innerHTML = lista.map((item, index) => {
        const idDetalhe = `detalhe-mot-${index}`;
        const isExpanded = motoristasExpandidos.has(item.motorista);
        const temDetalhes = item.detalhes_cidades && item.detalhes_cidades.length > 0;
        
        const motoristaEscaped = (item.motorista || '').replace(/'/g, "\\'");
        const platEscaped = (item.plataforma || '').replace(/'/g, "\\'");
        const itensCidades = temDetalhes ? item.detalhes_cidades.map(dc => {
            const cidEscaped = (dc.cidade || '').replace(/'/g, "\\'");
            return `
                <div class="bipados-detalhe-item">
                    <span class="bipados-detalhe-cidade">📍 ${dc.cidade}</span>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span class="bipados-detalhe-qtd">${dc.quantidade} ${dc.quantidade === 1 ? 'pacote' : 'pacotes'}</span>
                        <button type="button" onclick="event.stopPropagation(); abrirModalTransferenciaMotorista('${motoristaEscaped}', '${platEscaped}', ${item.quantidade || 0}, '${cidEscaped}')" style="background: rgba(2, 132, 199, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 4px; padding: 1px 6px; font-size: 0.65rem; font-weight: 800; cursor: pointer;" title="Transferir apenas os pacotes de ${dc.cidade} para outro motorista">
                            ⇄
                        </button>
                    </div>
                </div>
            `;
        }).join('') : `<div style="font-size: 0.72rem; color: #64748b; font-style: italic; padding: 4px 0;">Sem detalhamento por cidade</div>`;

        const htmlDetalhes = `
            <tr id="${idDetalhe}" class="bipados-detalhes-row" style="display: ${isExpanded ? 'table-row' : 'none'};">
                <td colspan="4">
                    <div class="bipados-detalhes-container">
                        <div class="bipados-detalhes-header" style="flex-wrap: wrap; gap: 6px;">
                            <span class="bipados-detalhes-titulo">
                                <span>📊</span> <strong>${item.motorista}</strong> <span style="color: #94a3b8; font-weight: 600;">(${item.quantidade} pcts)</span>
                            </span>
                            <button type="button" onclick="event.stopPropagation(); abrirModalTransferenciaMotorista('${motoristaEscaped}', '${platEscaped}', ${item.quantidade || 0})" style="background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; border: none; border-radius: 5px; padding: 3px 9px; font-size: 0.68rem; font-weight: 800; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; box-shadow: 0 2px 6px rgba(2, 132, 199, 0.3);" title="Transferir histórico deste motorista e lançar para outro motorista">
                                ⇄ Transferir Motorista
                            </button>
                        </div>
                        <div class="bipados-detalhes-grid">
                            ${itensCidades}
                        </div>
                    </div>
                </td>
            </tr>
        `;

        const itemEhAnjun = ehAnjun && ((item.plataforma || '').toLowerCase().includes('anjun') || (item.qtd_pendente || 0) > 0);
        const btnTransferRow = `
            <button type="button" onclick="event.stopPropagation(); abrirModalTransferenciaMotorista('${motoristaEscaped}', '${platEscaped}', ${item.quantidade || 0})" style="background: rgba(56, 189, 248, 0.14); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 4px; padding: 1px 5px; font-size: 0.7rem; font-weight: 900; cursor: pointer; margin-left: 5px; line-height: 1.2;" title="Transferir pacotes de ${motoristaEscaped} para outro motorista">
                ⇄
            </button>
        `;

        let col3Html = '';
        let col4Html = '';
        if (itemEhAnjun) {
            const qtdPend = item.qtd_pendente || 0;
            if (qtdPend > 0) {
                col3Html = `
                    <td class="bipados-col-plat" style="text-align: right; white-space: nowrap; padding: 4px 6px;">
                        <div style="display: flex; align-items: center; justify-content: flex-end; gap: 4px;">
                            <span style="background: rgba(34, 197, 94, 0.18); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); padding: 2px 5px; border-radius: 4px; font-weight: 800; font-size: 0.68rem;" title="${qtdPend} pacotes no grupo aberto">
                                🟢 ${qtdPend}
                            </span>
                            <button type="button" onclick="event.stopPropagation(); finalizarLoteDireto('${motoristaEscaped}')" style="background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; border: none; border-radius: 4px; padding: 2px 6px; font-size: 0.62rem; font-weight: 800; cursor: pointer; text-transform: uppercase;" title="Finalizar grupo aberto de ${motoristaEscaped}">
                                Finalizar
                            </button>
                            <button type="button" onclick="event.stopPropagation(); cancelarLoteDireto('${motoristaEscaped}')" style="background: rgba(148, 163, 184, 0.18); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 4px; padding: 1px 5px; font-size: 0.65rem; font-weight: 900; cursor: pointer; line-height: 1.2;" title="Cancelar/limpar lote aberto de ${motoristaEscaped} sem emitir folha no site">
                                ✕
                            </button>
                        </div>
                    </td>
                `;
            } else {
                col3Html = `
                    <td class="bipados-col-plat" style="text-align: right; padding: 4px 6px;">
                        <span style="color: #64748b; font-size: 0.68rem; font-weight: 600;">✔️ Fechado</span>
                    </td>
                `;
            }
            col4Html = `<td class="bipados-col-qtd" style="text-align: right; font-weight: 800; white-space: nowrap;">${item.quantidade}${btnTransferRow}</td>`;
        } else {
            col3Html = `<td class="bipados-col-plat">${item.plataforma || '---'}</td>`;
            col4Html = `<td class="bipados-col-qtd" style="white-space: nowrap;">${item.quantidade}${btnTransferRow}</td>`;
        }

        return `
            <tr class="bipados-motorista-row ${isExpanded ? 'bipados-row-expanded' : ''}" onclick="toggleDetalhesMotorista('${motoristaEscaped}')">
                <td class="bipados-col-motorista" title="Clique para ver detalhamento por cidade">
                    <span class="bipados-expand-icon">${isExpanded ? '▼' : '▶'}</span>
                    <span>${item.motorista}</span>
                </td>
                <td class="bipados-col-cidades" title="${item.cidades}">${item.cidades}</td>
                ${col3Html}
                ${col4Html}
            </tr>
            ${htmlDetalhes}
        `;
    }).join('');
}

function toggleDetalhesMotorista(motoristaNome) {
    if (!motoristaNome) return;
    if (motoristasExpandidos.has(motoristaNome)) {
        motoristasExpandidos.delete(motoristaNome);
    } else {
        motoristasExpandidos.add(motoristaNome);
    }
    aplicarOrdenacaoERenderizar();
}

// --- MODAL DE TRANSFERÊNCIA DE PACOTES ENTRE MOTORISTAS ---
let _transferContext = {
    motoristaOrigem: '',
    plataforma: '',
    quantidade: 0,
    listaMotoristasCandidatos: []
};

function popularSelectDestinoTransferencia(termoFiltro = '') {
    const sel = document.getElementById('transfer-destino-select');
    if (!sel) return;
    const norm = normalizarBuscaSidebar(termoFiltro || '');
    const filtrados = (_transferContext.listaMotoristasCandidatos || []).filter(m => {
        if (!m) return false;
        if (m.toLowerCase() === (_transferContext.motoristaOrigem || '').toLowerCase()) return false;
        if (!norm) return true;
        return normalizarBuscaSidebar(m).includes(norm);
    });

    if (filtrados.length === 0) {
        sel.innerHTML = `<option value="">Nenhum motorista encontrado para "${termoFiltro}"</option>`;
        return;
    }

    sel.innerHTML = `<option value="">-- Selecione o Novo Motorista (${filtrados.length}) --</option>` +
        filtrados.map(m => `<option value="${m}">${m}</option>`).join('');
    if (norm && filtrados.length > 0) {
        sel.value = filtrados[0];
    }
}

function renderizarListaPacotesTransferencia(pacotes, filtroSelecionado = 'TODAS') {
    const listaEl = document.getElementById('transfer-pacotes-lista');
    const actionsEl = document.getElementById('transfer-pacotes-actions');
    if (!listaEl) return;

    if (!Array.isArray(pacotes) || pacotes.length === 0) {
        listaEl.style.display = 'none';
        if (actionsEl) actionsEl.style.display = 'none';
        listaEl.innerHTML = '';
        return;
    }

    listaEl.style.display = 'flex';
    if (actionsEl) actionsEl.style.display = 'flex';

    const ehCodUnico = String(filtroSelecionado || '').startsWith('COD:');
    const codAlvo = ehCodUnico ? String(filtroSelecionado).slice(4).trim() : '';

    listaEl.innerHTML = pacotes.map(p => {
        const cod = String(p.codigo || '').trim();
        const cid = String(p.cidade || 'Não Informada').trim();
        const hora = String(p.horario || '').trim();
        let marcado = true;
        if (ehCodUnico) {
            marcado = (cod === codAlvo);
        } else if (filtroSelecionado && filtroSelecionado !== 'TODAS') {
            marcado = (cid.toLowerCase() === String(filtroSelecionado).toLowerCase());
        }
        return `
            <label style="display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 5px 8px; border-radius: 5px; background: rgba(30, 41, 59, 0.55); border: 1px solid rgba(51, 65, 85, 0.65); cursor: pointer; font-size: 0.78rem; user-select: none;">
                <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
                    <input type="checkbox" class="chk-transfer-pacote" value="${cod}" ${marcado ? 'checked' : ''} style="width: 15px; height: 15px; accent-color: #38bdf8; cursor: pointer; flex-shrink: 0;">
                    <span style="font-family: 'JetBrains Mono', monospace; font-weight: 800; color: #f8fafc; letter-spacing: 0.3px;">${cod}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
                    <span style="font-size: 0.7rem; color: #38bdf8; background: rgba(56, 189, 248, 0.12); padding: 1px 6px; border-radius: 4px; font-weight: 700;">${cid}</span>
                    ${hora ? `<span style="font-size: 0.68rem; color: #64748b;">${hora}</span>` : ''}
                </div>
            </label>
        `;
    }).join('');
}

async function abrirModalTransferenciaMotorista(motoristaOrigem, plataformaItem, qtdTotal, cidadePreSelecionada = 'TODAS') {
    const modal = document.getElementById('modal-transferir-motorista');
    if (!modal || !motoristaOrigem) return;

    const platNorm = (plataformaItem || (platformSelector ? platformSelector.value : '') || plataformaAtiva || 'anjun').toLowerCase();
    const chavePlat = platNorm.includes('imile') ? 'imile' : (platNorm.includes('loggi') ? 'loggi' : 'anjun');

    _transferContext = {
        motoristaOrigem,
        plataforma: chavePlat,
        quantidade: qtdTotal || 0,
        listaMotoristasCandidatos: [],
        pacotes: []
    };

    const elNome = document.getElementById('transfer-origem-nome');
    const elQtd = document.getElementById('transfer-origem-qtd');
    const elPlat = document.getElementById('transfer-plat-badge');
    const selCidade = document.getElementById('transfer-cidade-select');
    const inpBusca = document.getElementById('transfer-busca-destino');
    const chkSite = document.getElementById('transfer-chk-lancar-site');
    const boxSite = document.getElementById('transfer-box-lancar-site');
    const feedbackEl = document.getElementById('transfer-feedback-msg');

    if (elNome) elNome.innerText = motoristaOrigem;
    if (elQtd) elQtd.innerText = `${qtdTotal || 0} pacote(s)`;
    if (elPlat) elPlat.innerText = plataformaItem || chavePlat.toUpperCase();
    if (inpBusca) inpBusca.value = '';
    if (feedbackEl) feedbackEl.style.display = 'none';

    if (boxSite && chkSite) {
        if (chavePlat === 'anjun' || chavePlat === 'imile') {
            boxSite.style.display = 'flex';
            chkSite.checked = true;
        } else {
            boxSite.style.display = 'none';
            chkSite.checked = false;
        }
    }

    const regMot = (lotesFinalizadosCarregados || []).find(
        x => (x.motorista || '').toLowerCase() === motoristaOrigem.toLowerCase()
    );
    let pacotesMot = (regMot && Array.isArray(regMot.pacotes)) ? regMot.pacotes : [];

    // Fallback: se o lote ainda não veio com a lista de códigos, consulta o histórico do dia
    if (pacotesMot.length === 0) {
        try {
            const filterDateStart = document.getElementById('filter-date-start');
            const filterDateEnd = document.getElementById('filter-date-end');
            const dIni = (filterDateStart && filterDateStart.value) ? filterDateStart.value : obterDataHojeLocal();
            const dFim = (filterDateEnd && filterDateEnd.value) ? filterDateEnd.value : obterDataHojeLocal();
            const resHist = await fetch(`${API_URL}/historico?data_inicio=${encodeURIComponent(dIni)}&data_fim=${encodeURIComponent(dFim)}&_=${Date.now()}`);
            if (resHist.ok) {
                const histData = await resHist.json();
                const vistos = new Set();
                if (Array.isArray(histData)) {
                    histData.forEach(h => {
                        if (h && h.status === 'OK' && (h.motorista || '').toLowerCase() === motoristaOrigem.toLowerCase()) {
                            const cod = String(h.codigo || '').trim();
                            if (cod && !vistos.has(cod)) {
                                vistos.add(cod);
                                const ts = String(h.timestamp || '');
                                const hora = ts.includes('T') ? ts.split('T')[1].slice(0, 8) : ts.slice(-8);
                                pacotesMot.push({
                                    codigo: cod,
                                    cidade: (h.cidade && h.cidade !== '---') ? h.cidade : 'Não Informada',
                                    horario: hora
                                });
                            }
                        }
                    });
                }
            }
        } catch (_) {}
    }

    _transferContext.pacotes = pacotesMot;

    // Popula opções de cidade + códigos individuais dos pacotes no dropdown
    if (selCidade) {
        const dets = (regMot && Array.isArray(regMot.detalhes_cidades)) ? regMot.detalhes_cidades : [];
        let optsCid = `<option value="TODAS">Todos os pacotes deste motorista (${qtdTotal || pacotesMot.length || 0} pacotes)</option>`;
        dets.forEach(dc => {
            if (dc && dc.cidade) {
                optsCid += `<option value="${dc.cidade}">📍 Apenas ${dc.cidade} (${dc.quantidade} pacotes)</option>`;
            }
        });
        if (pacotesMot.length > 0) {
            optsCid += `<optgroup label="📦 Códigos dos Pacotes (${pacotesMot.length})">`;
            pacotesMot.forEach(p => {
                optsCid += `<option value="COD:${p.codigo}">📦 ${p.codigo} — ${p.cidade || 'Sem cidade'}</option>`;
            });
            optsCid += `</optgroup>`;
        }
        selCidade.innerHTML = optsCid;
        selCidade.value = cidadePreSelecionada || 'TODAS';
    }

    renderizarListaPacotesTransferencia(pacotesMot, cidadePreSelecionada || 'TODAS');

    modal.style.display = 'flex';

    // Carrega motoristas da plataforma (combinando lista do site + mapeados)
    const setNomes = new Set();
    if (Array.isArray(todosMotoristas)) {
        todosMotoristas.forEach(item => {
            const m = (item && item.motorista ? item.motorista : '').trim();
            if (m && m !== 'Sem Motorista') setNomes.add(m);
        });
    }
    try {
        const resSite = await fetch(`${API_URL}/motoristas/lista-site?plataforma=${encodeURIComponent(chavePlat)}&_=${Date.now()}`);
        if (resSite.ok) {
            const dataSite = await resSite.json();
            if (Array.isArray(dataSite.motoristas)) {
                dataSite.motoristas.forEach(m => {
                    const mLimpo = String(m || '').trim();
                    if (mLimpo && mLimpo !== 'Sem Motorista') setNomes.add(mLimpo);
                });
            }
        }
    } catch (_) {}

    if (chavePlat === 'loggi' && Array.isArray(todasCidades)) {
        todasCidades.forEach(c => {
            if (c) setNomes.add(c);
        });
    }

    _transferContext.listaMotoristasCandidatos = Array.from(setNomes).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
    popularSelectDestinoTransferencia('');
    if (inpBusca) inpBusca.focus();
}

const selTransferCidade = document.getElementById('transfer-cidade-select');
if (selTransferCidade) {
    selTransferCidade.addEventListener('change', (e) => {
        renderizarListaPacotesTransferencia(_transferContext.pacotes || [], e.target.value);
    });
}
const btnTransferMarcarTodos = document.getElementById('btn-transfer-marcar-todos');
if (btnTransferMarcarTodos) {
    btnTransferMarcarTodos.addEventListener('click', () => {
        document.querySelectorAll('.chk-transfer-pacote').forEach(chk => { chk.checked = true; });
        if (selTransferCidade) selTransferCidade.value = 'TODAS';
    });
}
const btnTransferDesmarcarTodos = document.getElementById('btn-transfer-desmarcar-todos');
if (btnTransferDesmarcarTodos) {
    btnTransferDesmarcarTodos.addEventListener('click', () => {
        document.querySelectorAll('.chk-transfer-pacote').forEach(chk => { chk.checked = false; });
    });
}

function fecharModalTransferenciaMotorista() {
    const modal = document.getElementById('modal-transferir-motorista');
    if (modal) modal.style.display = 'none';
    if (input) input.focus();
}

window.abrirModalTransferenciaMotorista = abrirModalTransferenciaMotorista;

const inpBuscaTransferDestino = document.getElementById('transfer-busca-destino');
if (inpBuscaTransferDestino) {
    inpBuscaTransferDestino.addEventListener('input', (e) => {
        popularSelectDestinoTransferencia(e.target.value);
    });
}
const btnFecharModalTransferir = document.getElementById('btn-fechar-modal-transferir');
if (btnFecharModalTransferir) {
    btnFecharModalTransferir.addEventListener('click', fecharModalTransferenciaMotorista);
}
const btnCancelarTransferir = document.getElementById('btn-cancelar-transferir');
if (btnCancelarTransferir) {
    btnCancelarTransferir.addEventListener('click', fecharModalTransferenciaMotorista);
}
const btnConfirmarTransferir = document.getElementById('btn-confirmar-transferir');
if (btnConfirmarTransferir) {
    btnConfirmarTransferir.addEventListener('click', async () => {
        const selDestino = document.getElementById('transfer-destino-select');
        const selCidade = document.getElementById('transfer-cidade-select');
        const chkSite = document.getElementById('transfer-chk-lancar-site');
        const feedbackEl = document.getElementById('transfer-feedback-msg');

        const motoristaDestino = selDestino ? selDestino.value.trim() : '';
        const cidadeFiltro = selCidade ? selCidade.value : 'TODAS';
        const lancarNoSite = chkSite ? chkSite.checked : false;

        if (!motoristaDestino) {
            alert('Selecione o novo motorista de destino.');
            if (selDestino) selDestino.focus();
            return;
        }

        const chks = Array.from(document.querySelectorAll('.chk-transfer-pacote'));
        const codigosMarcados = chks.filter(c => c.checked).map(c => c.value);
        if (chks.length > 0 && codigosMarcados.length === 0) {
            alert('Marque pelo menos 1 pacote para transferir.');
            return;
        }

        const filterDateStart = document.getElementById('filter-date-start');
        const filterDateEnd = document.getElementById('filter-date-end');

        btnConfirmarTransferir.disabled = true;
        const txtOrig = btnConfirmarTransferir.innerText;
        btnConfirmarTransferir.innerText = '⏳ TRANSFERINDO E LANÇANDO NO SITE...';

        if (feedbackEl) {
            feedbackEl.style.display = 'block';
            feedbackEl.style.background = 'rgba(2, 132, 199, 0.15)';
            feedbackEl.style.border = '1px solid rgba(56, 189, 248, 0.4)';
            feedbackEl.style.color = '#38bdf8';
            feedbackEl.innerText = `⏳ Transferindo ${codigosMarcados.length || ''} pacote(s) de ${_transferContext.motoristaOrigem} para ${motoristaDestino}... Aguarde...`;
        }

        try {
            const res = await fetch(`${API_URL}/atribuicao/transferir-motorista`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    motorista_origem: _transferContext.motoristaOrigem,
                    motorista_destino: motoristaDestino,
                    plataforma: _transferContext.plataforma,
                    cidade_filtro: (chks.length > 0 && codigosMarcados.length < chks.length) ? 'TODAS' : cidadeFiltro,
                    codigos_selecionados: (chks.length > 0 && codigosMarcados.length < chks.length) ? codigosMarcados : [],
                    lancar_no_site: lancarNoSite,
                    data_inicio: filterDateStart ? filterDateStart.value : '',
                    data_fim: filterDateEnd ? filterDateEnd.value : ''
                })
            });
            const data = await res.json();

            if (res.ok && data.status === 'sucesso') {
                emitirBeepSucesso();
                if (feedbackEl) {
                    feedbackEl.style.background = 'rgba(16, 185, 129, 0.18)';
                    feedbackEl.style.border = '1px solid rgba(16, 185, 129, 0.45)';
                    feedbackEl.style.color = '#4ade80';
                    feedbackEl.innerText = `✅ ${data.mensagem}`;
                }
                await carregarLotesFinalizados();
                const dStart = filterDateStart ? filterDateStart.value : obterDataHojeLocal();
                const dEnd = filterDateEnd ? filterDateEnd.value : obterDataHojeLocal();
                atualizarFechamentoData(dStart, dEnd);
                setTimeout(() => {
                    fecharModalTransferenciaMotorista();
                }, 1400);
            } else {
                emitirBeepErro();
                if (feedbackEl) {
                    feedbackEl.style.background = 'rgba(239, 68, 68, 0.18)';
                    feedbackEl.style.border = '1px solid rgba(239, 68, 68, 0.45)';
                    feedbackEl.style.color = '#f87171';
                    feedbackEl.innerText = `⚠️ ${data.mensagem || 'Erro ao transferir pacotes.'}`;
                }
            }
        } catch (e) {
            emitirBeepErro();
            if (feedbackEl) {
                feedbackEl.style.background = 'rgba(239, 68, 68, 0.18)';
                feedbackEl.style.border = '1px solid rgba(239, 68, 68, 0.45)';
                feedbackEl.style.color = '#f87171';
                feedbackEl.innerText = `⚠️ Erro de conexão: ${e.message}`;
            }
        } finally {
            btnConfirmarTransferir.disabled = false;
            btnConfirmarTransferir.innerText = txtOrig;
        }
    });
}

async function finalizarLoteDireto(motoristaNome) {
    if (!motoristaNome) return;
    if (!confirm(`Confirmar encerramento e emissão da folha de entrega para o motorista "${motoristaNome}" na Anjun?`)) {
        if (input) input.focus();
        return;
    }
    
    try {
        const res = await fetch(`${API_URL}/atribuicao/finalizar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motorista: motoristaNome, plataforma: 'anjun' })
        });
        const data = await res.json();
        if (res.ok) {
            if (driverSelect && driverSelect.value === motoristaNome) {
                if (atribuicaoCounter) atribuicaoCounter.innerText = "0 pacotes bipados";
                if (atribuicaoFeedback) atribuicaoFeedback.innerText = "Lote finalizado com sucesso";
            }
            carregarLotesFinalizados();
            alert(`Lote de "${motoristaNome}" finalizado com sucesso na Anjun!`);
        } else {
            alert("Erro ao finalizar lote: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (e) {
        alert("Erro de conexão: " + e.message);
    } finally {
        if (input) input.focus();
    }
}

async function cancelarLoteDireto(motoristaNome) {
    if (!motoristaNome) return;
    if (!confirm(`Deseja CANCELAR / LIMPAR o lote aberto de "${motoristaNome}" sem emitir folha na Anjun?`)) {
        if (input) input.focus();
        return;
    }

    try {
        const res = await fetch(`${API_URL}/atribuicao/cancelar-lote-anjun`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motorista: motoristaNome })
        });
        const data = await res.json();
        if (res.ok) {
            if (driverSelect && driverSelect.value === motoristaNome) {
                if (atribuicaoCounter) atribuicaoCounter.innerText = "0 pacotes bipados";
                if (atribuicaoFeedback) atribuicaoFeedback.innerText = "Lote aberto cancelado/limpo";
            }
            carregarLotesFinalizados();
        } else {
            alert("Erro ao cancelar lote: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (e) {
        alert("Erro de conexão: " + e.message);
    } finally {
        if (input) input.focus();
    }
}

async function finalizarTodosLotesAnjun() {
    const abertos = (lotesFinalizadosCarregados || []).filter(item => (item.qtd_pendente || 0) > 0);
    const qtdMot = abertos.length;
    const nomes = qtdMot > 0 ? abertos.map(a => `${a.motorista} (${a.qtd_pendente})`).join(', ') : 'Todos os lotes pendentes no site da Anjun';

    if (!confirm(`Deseja FINALIZAR TODOS os lotes abertos na Anjun de uma só vez?\n\nMotoristas: ${nomes}`)) {
        if (input) input.focus();
        return;
    }

    const btn = document.getElementById('btn-finalizar-todos-anjun');
    const txtOriginal = btn ? btn.innerText : '';
    if (btn) {
        btn.disabled = true;
        btn.innerText = '⏳ Finalizando...';
    }

    try {
        const res = await fetch(`${API_URL}/atribuicao/finalizar-todos-anjun`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: abertos.map(a => a.motorista) })
        });
        const data = await res.json();
        if (res.ok) {
            if (atribuicaoCounter) atribuicaoCounter.innerText = "0 pacotes bipados";
            if (atribuicaoFeedback) atribuicaoFeedback.innerText = "Todos os lotes finalizados";
            await carregarLotesFinalizados();
            if ((data.total_motoristas || 0) > 0) {
                const resumo = (data.motoristas || []).map(m => `${m.motorista} (${m.quantidade})`).join(', ');
                alert(`✅ ${data.total_motoristas} lote(s) finalizado(s) com sucesso na Anjun!\n\n${resumo}`);
            } else {
                alert("Não há lotes pendentes em aberto na Anjun no momento.");
            }
        } else {
            alert("Erro ao finalizar todos os lotes: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (e) {
        alert("Erro de conexão: " + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerText = txtOriginal || '✓ Finalizar Todos';
        }
        if (input) input.focus();
    }
}

async function cancelarTodosLotesAnjun() {
    const abertos = (lotesFinalizadosCarregados || []).filter(item => (item.qtd_pendente || 0) > 0);
    if (!confirm(`Deseja CANCELAR / LIMPAR todos os lotes abertos da lista sem emitir folha no site da Anjun?`)) {
        if (input) input.focus();
        return;
    }

    try {
        const res = await fetch(`${API_URL}/atribuicao/cancelar-lote-anjun`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ todos: true })
        });
        const data = await res.json();
        if (res.ok) {
            if (atribuicaoCounter) atribuicaoCounter.innerText = "0 pacotes bipados";
            if (atribuicaoFeedback) atribuicaoFeedback.innerText = "Lotes abertos limpos";
            await carregarLotesFinalizados();
        } else {
            alert("Erro ao cancelar lotes: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (e) {
        alert("Erro de conexão: " + e.message);
    } finally {
        if (input) input.focus();
    }
}

window.finalizarLoteDireto = finalizarLoteDireto;
window.cancelarLoteDireto = cancelarLoteDireto;
window.finalizarTodosLotesAnjun = finalizarTodosLotesAnjun;
window.cancelarTodosLotesAnjun = cancelarTodosLotesAnjun;
window.toggleDetalhesMotorista = toggleDetalhesMotorista;

// --- SISTEMA DE DIVERGÊNCIAS PENDENTES (CHECKLIST FÍSICA) ---

async function atualizarDivergenciasPendentes() {
    if (!divergenciasLog) return;
    try {
        const res = await fetch(`${API_URL}/divergencias/pendentes?_=${Date.now()}`);
        if (res.ok) {
            const lista = await res.json();
            renderizarDivergenciasPendentes(lista);
        }
    } catch (e) {
        console.error("Erro ao carregar divergências pendentes:", e);
    }
}

function renderizarDivergenciasPendentes(lista) {
    const sectionDiv = document.getElementById('section-divergencias');
    const badgeDiv = document.getElementById('badge-divergencias-count');
    const bottomGrids = document.querySelector('.bottom-grids');

    if (sectionDiv) sectionDiv.style.display = 'none';
    if (bottomGrids) bottomGrids.classList.remove('has-divergencias');
    if (badgeDiv) {
        const qtd = lista ? lista.length : 0;
        badgeDiv.innerText = `${qtd} pendência${qtd === 1 ? '' : 's'}`;
        badgeDiv.style.display = qtd > 0 ? 'inline-block' : 'none';
    }

    if (!lista || lista.length === 0) {
        if (divergenciasLog) {
            divergenciasLog.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align: center; color: #64748b; padding: 18px; font-style: italic; font-size: 0.78rem;">Nenhuma divergência pendente</td>
                </tr>
            `;
        }
        return;
    }

    divergenciasLog.innerHTML = lista.map(item => {
        const estavaEm = item.motorista_lote || item.estava_em || '---';
        const deveriaIr = item.motorista_esperado || item.deveria_ir_para || '---';
        return `
            <tr>
                <td style="font-family: monospace; color: #f87171; font-weight: bold; font-size: 0.82rem; cursor: pointer; transition: all 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 125px;" class="copyable-code" title="Clique para copiar (${item.codigo})">${item.codigo}</td>
                <td style="color: #cbd5e1; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px;" title="Estava com: ${estavaEm}">${estavaEm}</td>
                <td style="color: #4ade80; font-weight: bold; font-size: 0.82rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 135px;" title="Deveria ir para: ${deveriaIr}">${deveriaIr}</td>
            </tr>
        `;
    }).join('');
}

// Bloqueia e abre a tela de alerta gigante
function travarSistemaDivergencia(codigo, cidade, motoristaEsperado, motoristaLote) {
    sistemaTravado = true;
    const platAtual = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    
    if (divergenciaTexto) {
        if (platAtual === 'loggi') {
            divergenciaTexto.innerHTML = `
                O pacote <strong style="color: #f87171; font-family: monospace; font-size: 1.35rem;">${codigo}</strong> é da cidade <strong>${cidade}</strong>.<br><br>
                No entanto, este grupo da Loggi é restrito a: <strong style="color: #38bdf8; font-size: 1.25rem;">${motoristaEsperado || motoristaLote}</strong>!<br><br>
                <span style="color: #fbbf24; font-size: 1.05rem; font-weight: 800;">⚠️ NÃO MISTURE! SEPARE ESTE PACOTE DA PILHA/GAIOLA!</span>
            `;
        } else {
            divergenciaTexto.innerHTML = `
                O pacote <strong style="color: #f87171; font-family: monospace; font-size: 1.35rem;">${codigo}</strong> é da localidade <strong>${cidade}</strong> e pertence ao motorista <strong style="color: #38bdf8;">${motoristaEsperado}</strong>.<br><br>
                No entanto, você está bipando a pilha do motorista <strong style="color: #fb7185;">${motoristaLote}</strong>!
            `;
        }
    }
    
    if (divergenciaOverlay) {
        divergenciaOverlay.style.display = "flex";
    }
}

// Bloqueia a tela por falta de entrada do pacote no site
function travarSistemaSemEntrada(codigo, mensagem) {
    sistemaTravado = true;
    
    if (divergenciaTexto) {
        divergenciaTexto.innerHTML = `
            O pacote <strong style="color: #f87171; font-family: monospace; font-size: 1.35rem;">${codigo}</strong> falhou na atribuição!<br><br>
            Erro do Site: <strong style="color: #fb7185; font-size: 1.2rem;">${mensagem}</strong><br><br>
            <span style="color: #94a3b8; font-size: 0.95rem;">Por favor, verifique se a entrada deste pacote foi feita e clique em Enviar na Aba 1 antes de re-bipar.</span>
        `;
    }
    
    if (divergenciaOverlay) {
        divergenciaOverlay.style.display = "flex";
    }
}

// Bloqueia a tela por pacote duplicado nos últimos 30 dias
function travarSistemaDuplicado(codigo, timestamp, motorista, cidade) {
    sistemaTravado = true;
    
    if (divergenciaTexto) {
        divergenciaTexto.innerHTML = `
            O pacote <strong style="color: #f87171; font-family: monospace; font-size: 1.35rem;">${codigo}</strong> já foi bipado anteriormente!<br><br>
            Data do Lançamento: <strong style="color: #38bdf8;">${timestamp}</strong><br>
            Motorista: <strong style="color: #4ade80;">${motorista}</strong><br>
            Cidade: <strong style="color: #fb7185;">${cidade}</strong><br><br>
            <span style="color: #f87171; font-weight: bold; font-size: 0.95rem;">ATENÇÃO: Este pacote já foi processado! Não coloque na pilha novamente.</span>
        `;
    }
    
    if (divergenciaOverlay) {
        divergenciaOverlay.style.display = "flex";
    }
}

// Destrava a tela e volta o foco para o leitor
function destravarSistema() {
    sistemaTravado = false;
    if (divergenciaOverlay) {
        divergenciaOverlay.style.display = "none";
    }
    
    statusPanel.className = 'status-container awaiting';
    statusLabel.innerText = "AGUARDANDO BIP";
    subStatusLabel.innerText = "Aponte o leitor para o QR Code do produto";
    
    if (input) {
        input.value = "";
        input.focus();
    }
}

if (btnDestravar) {
    btnDestravar.addEventListener('click', destravarSistema);
}

// --- CONTROLE DE SESSÃO / NÃO SOU ROBÔ / AUTO-PAUSE & AUTO-RESUME ---
let monitoramentoLoginInterval = null;
let aguardandoLoginAtivo = false;

function mostrarOverlayAguardandoLogin(msg, plataforma = 'anjun') {
    aguardandoLoginAtivo = true;
    const platLower = (plataforma || '').toLowerCase();
    const isLoggi = platLower.includes('loggi');
    const isImile = platLower.includes('imile');
    const modal = document.getElementById('modal-aguardando-login');
    const msgEl = document.getElementById('modal-aguardando-login-msg');
    const tituloEl = document.getElementById('modal-aguardando-login-titulo');
    
    if (tituloEl) {
        tituloEl.innerText = isLoggi ? "SESSÃO DESCONECTADA (LOGGI)" : (isImile ? "SESSÃO DESCONECTADA (IMILE)" : "SESSÃO DESCONECTADA / ROBÔ");
    }
    if (msgEl) {
        if (msg) {
            msgEl.innerHTML = msg;
        } else {
            msgEl.innerHTML = isLoggi
                ? "A sessão da Loggi expirou. Clique em <strong>'Entrar com o Google'</strong> no Chrome para continuar."
                : (isImile
                    ? "A sessão da iMile expirou. Faça o <strong>login novamente</strong> no Chrome para continuar."
                    : "A sessão da Anjun expirou ou solicitou validação do <strong>'Não sou robô'</strong> no Chrome.");
        }
    }
    if (modal) {
        modal.style.display = 'flex';
    }
    if (statusPanel) {
        statusPanel.className = 'status-container awaiting';
    }
    if (statusLabel) {
        statusLabel.innerText = "SESSÃO DESCONECTADA";
    }
    if (subStatusLabel) {
        const filaQtd = filaBipes.length;
        const acao = isLoggi ? "Clique em 'Entrar com o Google'" : (isImile ? "Faça login na iMile" : "Resolva o 'Não sou robô'");
        subStatusLabel.innerText = `${acao} no Chrome [${filaQtd} pacote(s) na fila]...`;
    }
    if (input) {
        input.focus();
    }
}

function esconderOverlayAguardandoLogin() {
    aguardandoLoginAtivo = false;
    const modal = document.getElementById('modal-aguardando-login');
    if (modal) {
        modal.style.display = 'none';
    }
}

function iniciarMonitoramentoLogin(plataforma = 'anjun') {
    if (monitoramentoLoginInterval) return;
    
    const platLower = (plataforma || 'anjun').toLowerCase();
    const isLoggi = platLower.includes('loggi');
    const isImile = platLower.includes('imile');
    const platNome = isLoggi ? 'Loggi' : (isImile ? 'iMile' : 'Anjun');
    console.log(`[*] [Sessão] Iniciando monitoramento da sessão ${platNome} no Chrome...`);
    monitoramentoLoginInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_URL}/sessao/status?plataforma=${encodeURIComponent(plataforma)}`);
            if (resp.ok) {
                const dados = await resp.json();
                if (dados.status === 'conectado' && dados.logado === true) {
                    console.log(`[+] [Sessão] Reconexão detectada com sucesso na ${platNome}! Retomando fila de bipes...`);
                    clearInterval(monitoramentoLoginInterval);
                    monitoramentoLoginInterval = null;
                    esconderOverlayAguardandoLogin();
                    emitirBeepSucesso();
                    falarCidade(`Sessão da ${platNome} reestabelecida. Continuando bipagem.`);
                    
                    // Retoma o processamento da fila com pequeno delay para estabilização
                    setTimeout(() => {
                        processandoFila = false;
                        if (filaBipes.length > 0) {
                            processarProximoDaFila();
                        } else {
                            statusPanel.className = 'status-container awaiting';
                            statusLabel.innerText = "AGUARDANDO BIP";
                            subStatusLabel.innerText = "Aponte o leitor para o QR Code do produto";
                        }
                    }, 600);
                }
            }
        } catch (e) {
            console.warn("[!] Erro ao checar status da sessão:", e);
        }
    }, 2000);
}

// --- PREPARAÇÃO DO CHROME E MODAL DE CONFIRMAÇÃO DE MOTORISTA ---
let preparandoSessao = false;

async function prepararSessaoEMostrarConfirmacao(motorista, plataforma, qtdPendentes, isRecuperado = false) {
    if (preparandoSessao) return;
    preparandoSessao = true;
    processandoFila = false;

    const platAlvo = plataforma || platformSelector.value || "anjun";
    const motAlvo = motorista || (driverSelect ? driverSelect.value : "");
    const platNome = todasPlataformas[platAlvo]?.nome || platAlvo.toUpperCase();

    // 1. Atualiza na tela de status que o Chrome está sendo aberto e o motorista posicionado no site
    statusPanel.className = 'status-container awaiting';
    statusLabel.innerText = "ABRINDO CHROME...";
    subStatusLabel.innerText = `Iniciando navegador e posicionando motorista '${motAlvo || 'Sem Motorista'}' no site... Aguarde...`;
    if (atribuicaoFeedback) {
        atribuicaoFeedback.innerText = `Abrindo o Chrome para ${motAlvo || 'Sem Motorista'}...`;
        atribuicaoFeedback.style.color = "#38bdf8";
    }

    try {
        // 2. Chama o backend para abrir o Chrome, logar e colocar o motorista na tela do site
        const resposta = await fetch(`${API_URL}/recuperar-sessao-motorista`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plataforma: platAlvo,
                motorista: motAlvo
            })
        });
        const res = await resposta.json();
        console.log("[+] Chrome aberto e motorista preparado no site:", res);
    } catch (e) {
        console.warn("[!] Erro ao tentar preparar sessão no Chrome:", e);
    } finally {
        preparandoSessao = false;
    }

    // 3. AGORA que o Chrome já abriu, logou e colocou o motorista na tela do site:
    // Exibe o modal para o operador conferir no Chrome e na tela antes de prosseguir com os bipes!
    exibirModalConfirmacaoMotorista(motAlvo, platAlvo, qtdPendentes, isRecuperado);
}

function exibirModalConfirmacaoMotorista(motoristaAtual, plataforma, qtdPendentes, isRecuperado = false) {
    modalConfirmacaoAberto = true;
    plataformaConfirmacaoPendente = plataforma || platformSelector.value || "anjun";

    if (modalConfirmTitulo) {
        modalConfirmTitulo.innerText = isRecuperado ? "PACOTES PENDENTES DETECTADOS" : "CONFIRMAR MOTORISTA (CHROME ABERTO)";
    }
    if (modalConfirmSubtitulo) {
        modalConfirmSubtitulo.innerText = "O Chrome foi aberto e o motorista foi posicionado no site";
    }
    if (modalConfirmDesc) {
        const platNome = todasPlataformas[plataformaConfirmacaoPendente]?.nome || plataformaConfirmacaoPendente.toUpperCase();
        modalConfirmDesc.innerHTML = `O Chrome está aberto na plataforma <strong style="color: #38bdf8;">${platNome}</strong> com o motorista selecionado no site.<br><br>Confira na tela do Chrome se o motorista está correto. Existem <strong style="color: #f59e0b;">${qtdPendentes} pacote(s) pendente(s)</strong> na fila.<br>Se precisar corrigir, selecione o motorista correto abaixo e clique em <strong>Prosseguir</strong>:`;
    }
    if (modalConfirmPlat) {
        modalConfirmPlat.innerText = todasPlataformas[plataformaConfirmacaoPendente]?.nome || plataformaConfirmacaoPendente.toUpperCase();
    }
    if (modalConfirmQtd) {
        modalConfirmQtd.innerText = `${qtdPendentes} pacote(s)`;
    }

    if (modalConfirmDriverSelect) {
        if (driverSelect && driverSelect.innerHTML.trim() && (platformSelector.value === plataformaConfirmacaoPendente)) {
            modalConfirmDriverSelect.innerHTML = driverSelect.innerHTML;
        } else if (plataformaConfirmacaoPendente === 'loggi') {
            const cidadesOrdenadas = Array.from(new Set(todasCidades)).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            modalConfirmDriverSelect.innerHTML = '<option value="">Apenas Entrada (Sem Atribuição)</option>' + 
                cidadesOrdenadas.map(c => `<option value="${c}">${c}</option>`).join('');
        } else {
            const motoristasList = Array.isArray(todosMotoristas) 
                ? todosMotoristas.map(m => m.motorista) 
                : Object.values(todosMotoristas);
            const motoristasSet = new Set(motoristasList.map(m => (m || '').trim()).filter(m => m && m !== "Sem Motorista"));
            const motoristasOrdenados = Array.from(motoristasSet).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            modalConfirmDriverSelect.innerHTML = '<option value="">-- Selecione o Motorista Correto --</option>' + 
                motoristasOrdenados.map(m => `<option value="${m}">${m}</option>`).join('');
        }

        const motValor = motoristaAtual || (driverSelect ? driverSelect.value : "");
        if (motValor) {
            let existe = false;
            for (let opt of modalConfirmDriverSelect.options) {
                if (opt.value === motValor) {
                    existe = true;
                    break;
                }
            }
            if (!existe) {
                const newOpt = document.createElement('option');
                newOpt.value = motValor;
                newOpt.innerText = `${motValor} (Atual)`;
                modalConfirmDriverSelect.appendChild(newOpt);
            }
            modalConfirmDriverSelect.value = motValor;
        }
    }

    if (modalConfirmarMotorista) {
        modalConfirmarMotorista.style.display = "flex";
    }

    if (btnModalConfirmContinuar) {
        btnModalConfirmContinuar.focus();
    }
}

function fecharModalConfirmacaoMotorista() {
    modalConfirmacaoAberto = false;
    if (modalConfirmarMotorista) {
        modalConfirmarMotorista.style.display = "none";
    }
    if (input && !sistemaTravado) {
        input.value = "";
        input.focus();
    }
}

if (btnModalConfirmContinuar) {
    btnModalConfirmContinuar.addEventListener('click', async () => {
        const motoristaEscolhido = modalConfirmDriverSelect ? modalConfirmDriverSelect.value : "";
        const platAlvo = plataformaConfirmacaoPendente || platformSelector.value || "anjun";

        if (!motoristaEscolhido && (platAlvo === 'anjun' || platAlvo === 'imile' || platAlvo === 'loggi')) {
            alert("Por favor, selecione um motorista/destino válido antes de continuar.");
            if (modalConfirmDriverSelect) modalConfirmDriverSelect.focus();
            return;
        }

        // Se o operador alterou o motorista no modal para um diferente:
        const motAtualFila = filaBipes[0]?.motorista;
        if (motoristaEscolhido !== motAtualFila) {
            statusPanel.className = 'status-container awaiting';
            statusLabel.innerText = "ALTERANDO MOTORISTA...";
            subStatusLabel.innerText = `Atualizando motorista no Chrome para '${motoristaEscolhido}'...`;
            try {
                await fetch(`${API_URL}/recuperar-sessao-motorista`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        plataforma: platAlvo,
                        motorista: motoristaEscolhido
                    })
                });
            } catch (e) {
                console.warn("[!] Falha ao trocar motorista no Chrome:", e);
            }
        }

        // Atualiza todos os pacotes da fila com o motorista confirmado/alterado
        filaBipes.forEach(item => {
            item.motorista = motoristaEscolhido || null;
            item.plataforma = platAlvo;
        });
        salvarFilaNoLocalStorage();

        // Atualiza na tela principal
        if (driverSelect) {
            driverSelect.value = motoristaEscolhido;
            atualizarCidadesDoMotoristaSelecionado();
        }

        confirmadoReaberturaAtivo = true;
        fecharModalConfirmacaoMotorista();

        statusPanel.className = 'status-container awaiting';
        statusLabel.innerText = "RETOMANDO FILA...";
        subStatusLabel.innerText = `Processando ${filaBipes.length} pacote(s) para ${motoristaEscolhido || 'Sem Atribuição'}...`;

        if (!processandoFila) {
            processarProximoDaFila();
        }
    });
}

if (btnModalConfirmLimpar) {
    btnModalConfirmLimpar.addEventListener('click', () => {
        const qtd = filaBipes.length;
        if (!confirm(`Deseja realmente descartar e limpar todos os ${qtd} pacote(s) pendente(s) da fila?`)) {
            return;
        }

        filaBipes.length = 0;
        salvarFilaNoLocalStorage();
        processandoFila = false;
        confirmadoReaberturaAtivo = false;

        fecharModalConfirmacaoMotorista();

        statusPanel.className = 'status-container awaiting';
        statusLabel.innerText = "AGUARDANDO BIP";
        subStatusLabel.innerText = `Fila de ${qtd} pacote(s) pendente(s) descartada com sucesso.`;

        if (input) {
            input.value = "";
            input.focus();
        }
    });
}

// Atalho de teclado para destravar (Enter ou Esc) e modal de confirmação
window.addEventListener('keydown', (e) => {
    if (modalConfirmacaoAberto) {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (btnModalConfirmContinuar) btnModalConfirmContinuar.click();
            return;
        }
    }
    if (sistemaTravado && (e.key === 'Enter' || e.key === 'Escape')) {
        e.preventDefault();
        destravarSistema();
    }
});

// Polling suave a cada 5 segundos para manter a lista de divergências atualizada
setInterval(atualizarDivergenciasPendentes, 5000);

// Mostra a lista de cidades correspondente ao motorista selecionado
function atualizarCidadesDoMotoristaSelecionado() {
    if (!driverCitiesListBox) return;
    const platSelecionada = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    const activeDriverNameDisplay = document.getElementById('active-driver-name-display');
    const driverCitiesCountBadge = document.getElementById('driver-cities-count-badge');
    const driverCitiesSection = document.getElementById('driver-cities-section');
    const containerLoggiCities = document.getElementById('container-loggi-cities');
    
    if (platSelecionada === 'loggi') {
        if (driverCitiesSection) driverCitiesSection.style.display = 'none';
        if (containerLoggiCities) containerLoggiCities.style.display = 'flex';
        const txtGrupoAtivo = (badgeGrupoLoggiTexto ? badgeGrupoLoggiTexto.innerText.replace('🟢 Grupo Ativo:', '').trim() : '');
        if (activeDriverNameDisplay) {
            if (txtGrupoAtivo && txtGrupoAtivo !== 'Aguardando bipe...') {
                activeDriverNameDisplay.innerText = txtGrupoAtivo;
            } else {
                activeDriverNameDisplay.innerText = cidadesLoggiSelecionadas.length > 0 ? `${cidadesLoggiSelecionadas[0]} (Grupo Loggi)` : "Nenhuma cidade selecionada";
            }
        }
        return;
    }

    if (driverCitiesSection) driverCitiesSection.style.display = 'flex';
    if (containerLoggiCities) containerLoggiCities.style.display = 'none';
    
    const motorista = driverSelect ? driverSelect.value : "";
    if (activeDriverNameDisplay) {
        activeDriverNameDisplay.innerText = motorista || "Apenas Entrada (Sem Atribuição)";
    }
    if (!motorista) {
        driverCitiesListBox.innerHTML = `<span style="color: #64748b; font-style: italic; font-weight: normal; font-size: 0.78rem; padding: 4px;">Selecione um motorista na lista ao lado</span>`;
        if (driverCitiesCountBadge) driverCitiesCountBadge.innerText = '0 cidades';
        return;
    }
    const cidades = [];
    if (Array.isArray(todosMotoristas)) {
        for (const item of todosMotoristas) {
            if (item.motorista && item.motorista.trim().toLowerCase() === motorista.trim().toLowerCase()) {
                const cidLimpa = (item.cidade || '').trim();
                const cepLimpo = (item.faixa_cep || '').trim();
                if (cidLimpa && !['sem cidade', 'geral'].includes(cidLimpa.toLowerCase())) {
                    const label = cepLimpo ? `${cidLimpa} (CEP: ${cepLimpo})` : cidLimpa;
                    if (!cidades.includes(label)) {
                        cidades.push(label);
                    }
                }
            }
        }
    } else {
        for (const [cidade, mot] of Object.entries(todosMotoristas)) {
            if (mot.trim().toLowerCase() === motorista.trim().toLowerCase()) {
                const cidLimpa = (cidade || '').trim();
                if (cidLimpa && !['sem cidade', 'geral'].includes(cidLimpa.toLowerCase()) && !cidades.includes(cidLimpa)) {
                    cidades.push(cidLimpa);
                }
            }
        }
    }
    
    if (cidades.length > 0) {
        cidades.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
        if (driverCitiesCountBadge) driverCitiesCountBadge.innerText = `${cidades.length} ${cidades.length === 1 ? 'cidade' : 'cidades'}`;
        driverCitiesListBox.innerHTML = cidades.map(c => `
            <span class="driver-city-badge">
                📍 ${c}
            </span>
        `).join('');
    } else {
        if (driverCitiesCountBadge) driverCitiesCountBadge.innerText = '0 cidades';
        driverCitiesListBox.innerHTML = `<span style="color: #f87171; font-size: 0.78rem; font-weight: 700; padding: 4px;">Nenhuma cidade vinculada a este motorista</span>`;
    }
}

async function atualizarContagemAoMudarMotorista() {
    atualizarCidadesDoMotoristaSelecionado();
    
    const motorista = driverSelect ? driverSelect.value : "";
    if (!motorista) {
        atribuicaoCounter.innerText = "0 pacotes bipados";
        atribuicaoFeedback.innerText = "Aguardando início...";
        return;
    }
    
    try {
        const res = await fetch(`${API_URL}/atribuicao/status?_=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            if (data.motorista && data.motorista.toLowerCase() === motorista.toLowerCase()) {
                atribuicaoCounter.innerText = `${data.contagem} PACOTES BIPADOS`;
                atribuicaoFeedback.innerText = `Lote em andamento`;
            } else {
                atribuicaoCounter.innerText = "0 pacotes bipados";
                atribuicaoFeedback.innerText = `Pronto para bipar`;
            }
        }
    } catch (e) {
        atribuicaoCounter.innerText = "0 pacotes bipados";
    }
}

if (driverSelect) {
    driverSelect.addEventListener('change', () => {
        driverSelect.blur();
        atualizarContagemAoMudarMotorista();
        if (input) input.focus();
    });
}

// ========================================================
// LÓGICA DO MODAL DE CONFIGURAÇÕES (Cidades, Motoristas, Credenciais)
// ========================================================
const settingsModal = document.getElementById('settings-modal');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnAbrirConfiguracoes = document.getElementById('btn-abrir-configuracoes') || document.getElementById('btn-abrir-credenciais');

// Elementos da Aba Cidades
const cidadesListBody = document.getElementById('cidades-list-body');
const formCidade = document.getElementById('form-cidade');
const cidNome = document.getElementById('cid-nome');

// Elementos da Aba Motoristas
const motoristaPlataformaSelect = document.getElementById('motorista-plataforma-select');
const motoristasListBody = document.getElementById('motoristas-list-body');
const filtroMapeamentosModal = document.getElementById('filtro-mapeamentos-modal');
const btnLimparFiltroMapeamentos = document.getElementById('btn-limpar-filtro-mapeamentos');
const contadorMapeamentosModal = document.getElementById('contador-mapeamentos-modal');
const formMotorista = document.getElementById('form-motorista');
const formMotoristaTitulo = document.getElementById('form-motorista-titulo');
const motCidadeSelect = document.getElementById('mot-cidade-select');
const motCepInput = document.getElementById('mot-cep-input');
const motNomeSelect = document.getElementById('mot-nome-select');
const motBuscaSiteInput = document.getElementById('mot-busca-site-input');
const btnAtualizarMotoristasSite = document.getElementById('btn-atualizar-motoristas-site');
const motNomeManualGroup = document.getElementById('mot-nome-manual-group');
const motNome = document.getElementById('mot-nome');
const btnSalvarMapeamentoMot = document.getElementById('btn-salvar-mapeamento-mot');
const btnCancelarEdicaoMot = document.getElementById('btn-cancelar-edicao-mot');

// Elementos da Aba Credenciais
const modalPlatSelector = document.getElementById('modal-plat-selector');
const modalLoginUser = document.getElementById('modal-login-user');
const modalLoginPass = document.getElementById('modal-login-pass');
const btnModalSalvar = document.getElementById('btn-modal-salvar');

let motoristasPlataformaModal = [];
let motoristasSiteModalLista = [];
let indexEdicaoMapeamentoModal = null;

// Abertura e Fechamento do Modal
function abrirModalConfiguracoes(tabInicial = 'tab-cidades') {
    if (!settingsModal) return;
    
    // Configura abas
    const tabs = settingsModal.querySelectorAll('.tab-link');
    const contents = settingsModal.querySelectorAll('.tab-content');
    tabs.forEach(t => {
        if (t.getAttribute('data-tab') === tabInicial) t.classList.add('active');
        else t.classList.remove('active');
    });
    contents.forEach(c => {
        if (c.id === tabInicial) c.classList.add('active');
        else c.classList.remove('active');
    });

    renderizarListaCidadesModal();
    popularMotoristaPlataformaDropdownModal();
    atualizarMotoristasPlataformaModal();
    popularCredenciaisPlataformaModal();

    settingsModal.classList.add('active');
    settingsModal.style.display = 'flex';
}

async function fecharModalConfiguracoes() {
    if (settingsModal) {
        settingsModal.classList.remove('active');
        settingsModal.style.display = 'none';
    }
    if (!plataformaAtiva && (!platformSelector || !platformSelector.value) && motoristaPlataformaSelect && motoristaPlataformaSelect.value && todasPlataformas[motoristaPlataformaSelect.value]) {
        plataformaAtiva = motoristaPlataformaSelect.value;
        if (platformSelector) platformSelector.value = motoristaPlataformaSelect.value;
    }
    await carregarConfiguracoes();
    if (input) input.focus();
}

if (btnAbrirConfiguracoes) {
    btnAbrirConfiguracoes.addEventListener('click', (e) => {
        e.preventDefault();
        abrirModalConfiguracoes('tab-cidades');
    });
}

if (btnCloseModal) {
    btnCloseModal.addEventListener('click', fecharModalConfiguracoes);
}

// Fechar ao clicar fora do modal
if (settingsModal) {
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            fecharModalConfiguracoes();
        }
    });
}

// Fechar ao pressionar Escape
window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && settingsModal && (settingsModal.classList.contains('active') || settingsModal.style.display === 'flex')) {
        fecharModalConfiguracoes();
    }
});

// Alternância de Abas
if (settingsModal) {
    const tabs = settingsModal.querySelectorAll('.tab-link');
    const contents = settingsModal.querySelectorAll('.tab-content');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            const tabId = tab.getAttribute('data-tab');
            const targetContent = document.getElementById(tabId);
            if (targetContent) targetContent.classList.add('active');
            if (tabId === 'tab-cidades') {
                renderizarListaCidadesModal();
            } else if (tabId === 'tab-motoristas') {
                renderizarListaCidadesModal();
                atualizarMotoristasPlataformaModal();
            }
        });
    });
}

// ----------------------------------------------------
// ABA CIDADES
// ----------------------------------------------------
function renderizarListaCidadesModal() {
    if (!cidadesListBody) return;
    todasCidades.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));

    if (todasCidades.length === 0) {
        cidadesListBody.innerHTML = '<tr><td colspan="2" style="text-align: center; color: #64748b;">Nenhuma cidade cadastrada.</td></tr>';
        if (motCidadeSelect) motCidadeSelect.innerHTML = '<option value="">Nenhuma cidade cadastrada</option>';
        return;
    }

    cidadesListBody.innerHTML = todasCidades.map(cidade => {
        const escapedCidade = cidade.replace(/'/g, "\\'");
        return `
            <tr>
                <td style="font-weight: 600; color: #f8fafc;">${cidade}</td>
                <td style="text-align: right;">
                    <button type="button" class="btn-row-action" style="color: #38bdf8; margin-right: 12px;" onclick="editarCidadeModal('${escapedCidade}')">Editar</button>
                    <button type="button" class="btn-row-action" style="color: #ef4444;" onclick="deletarCidadeModal('${escapedCidade}')">Deletar</button>
                </td>
            </tr>
        `;
    }).join('');

    if (motCidadeSelect) {
        motCidadeSelect.innerHTML = '<option value="">Selecione uma cidade...</option>' + 
            todasCidades.map(c => `<option value="${c}">${c}</option>`).join('');
    }
}

async function salvarNovaCidadeModal(e) {
    e.preventDefault();
    if (!cidNome) return;
    const cidade = cidNome.value.trim();
    if (!cidade) return;

    if (todasCidades.some(c => c.toLowerCase() === cidade.toLowerCase())) {
        alert(`A cidade "${cidade}" já está cadastrada.`);
        return;
    }

    todasCidades.push(cidade);
    todasCidades.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));

    try {
        const res = await fetch(`${API_URL}/salvar-cidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cidades: todasCidades })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            if (Array.isArray(data.cidades)) {
                todasCidades = data.cidades
                    .map(c => String(c || '').trim())
                    .filter(Boolean)
                    .sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            }
            cidNome.value = '';
            renderizarListaCidadesModal();
            await carregarConfiguracoes();
        } else {
            alert("Erro ao salvar cidade: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
}

if (formCidade) {
    formCidade.addEventListener('submit', salvarNovaCidadeModal);
}

function customPrompt(title, message, defaultValue = '') {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-prompt-modal');
        const titleEl = document.getElementById('prompt-modal-title');
        const msgEl = document.getElementById('prompt-modal-message');
        const inputEl = document.getElementById('prompt-modal-input');
        const btnCancel = document.getElementById('prompt-modal-btn-cancel');
        const btnConfirm = document.getElementById('prompt-modal-btn-confirm');

        if (!modal || !inputEl) {
            const val = prompt(message, defaultValue);
            return resolve(val);
        }
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }

        titleEl.innerHTML = `<span>✏️</span> ${title}`;
        msgEl.innerText = message;
        inputEl.style.display = 'block';
        inputEl.value = defaultValue;
        btnCancel.style.display = 'inline-block';
        btnConfirm.innerText = 'Salvar';
        btnConfirm.style.background = '#0284c7';
        modal.style.zIndex = '9999999';
        modal.style.display = 'flex';
        setTimeout(() => {
            inputEl.focus();
            inputEl.select();
        }, 50);

        const cleanup = () => {
            modal.style.display = 'none';
            btnCancel.onclick = null;
            btnConfirm.onclick = null;
            inputEl.onkeydown = null;
            setTimeout(() => {
                const settingsModal = document.getElementById('settings-modal');
                const settingsOpen = settingsModal && settingsModal.style.display && settingsModal.style.display !== 'none';
                if (!settingsOpen && input) input.focus();
            }, 40);
        };

        btnCancel.onclick = () => { cleanup(); resolve(null); };
        btnConfirm.onclick = () => { const val = inputEl.value; cleanup(); resolve(val); };
        inputEl.onkeydown = (e) => {
            if (e.key === 'Enter') { const val = inputEl.value; cleanup(); resolve(val); }
            else if (e.key === 'Escape') { cleanup(); resolve(null); }
        };
    });
}

function customConfirm(title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-prompt-modal');
        const titleEl = document.getElementById('prompt-modal-title');
        const msgEl = document.getElementById('prompt-modal-message');
        const inputEl = document.getElementById('prompt-modal-input');
        const btnCancel = document.getElementById('prompt-modal-btn-cancel');
        const btnConfirm = document.getElementById('prompt-modal-btn-confirm');

        if (!modal) {
            const val = confirm(message);
            return resolve(val);
        }
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }

        titleEl.innerHTML = `<span>🗑️</span> ${title}`;
        msgEl.innerText = message;
        inputEl.style.display = 'none';
        btnCancel.style.display = 'inline-block';
        btnConfirm.innerText = 'Excluir';
        btnConfirm.style.background = '#ef4444';
        modal.style.zIndex = '9999999';
        modal.style.display = 'flex';
        btnConfirm.focus();

        const cleanup = () => {
            modal.style.display = 'none';
            btnCancel.onclick = null;
            btnConfirm.onclick = null;
            setTimeout(() => {
                const settingsModal = document.getElementById('settings-modal');
                const settingsOpen = settingsModal && settingsModal.style.display && settingsModal.style.display !== 'none';
                if (!settingsOpen && input) input.focus();
            }, 40);
        };

        btnCancel.onclick = () => { cleanup(); resolve(false); };
        btnConfirm.onclick = () => { cleanup(); resolve(true); };
    });
}

function customAlert(title, message) {
    return new Promise((resolve) => {
        const modal = document.getElementById('custom-prompt-modal');
        const titleEl = document.getElementById('prompt-modal-title');
        const msgEl = document.getElementById('prompt-modal-message');
        const inputEl = document.getElementById('prompt-modal-input');
        const btnCancel = document.getElementById('prompt-modal-btn-cancel');
        const btnConfirm = document.getElementById('prompt-modal-btn-confirm');

        if (!modal) {
            return resolve(true);
        }
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }

        titleEl.innerHTML = `<span>🔔</span> ${title || 'Aviso'}`;
        msgEl.innerText = message || '';
        inputEl.style.display = 'none';
        btnCancel.style.display = 'none';
        btnConfirm.innerText = 'OK';
        btnConfirm.style.background = '#0284c7';
        modal.style.zIndex = '9999999';
        modal.style.display = 'flex';
        setTimeout(() => btnConfirm.focus(), 30);

        const cleanup = () => {
            modal.style.display = 'none';
            btnConfirm.onclick = null;
            btnConfirm.onkeydown = null;
            setTimeout(() => {
                const settingsModal = document.getElementById('settings-modal');
                const settingsOpen = settingsModal && settingsModal.style.display && settingsModal.style.display !== 'none';
                if (!settingsOpen && input) input.focus();
            }, 40);
        };

        btnConfirm.onclick = () => { cleanup(); resolve(true); };
        btnConfirm.onkeydown = (e) => {
            if (e.key === 'Enter' || e.key === 'Escape' || e.key === ' ') {
                e.preventDefault();
                cleanup();
                resolve(true);
            }
        };
    });
}

// Substitui window.alert nativo (que no Electron/Windows trava o foco do teclado até minimizar/maximizar)
window.alert = (msg) => {
    customAlert('Aviso do Sistema', String(msg || ''));
};

window.editarCidadeModal = async (cidadeAntiga) => {
    const novaCidade = await customPrompt("Editar Cidade", `Informe o novo nome para a cidade:`, cidadeAntiga);
    if (novaCidade === null) return;
    
    const novaCidadeTrim = novaCidade.trim();
    if (!novaCidadeTrim) {
        alert("O nome da cidade não pode ser vazio.");
        return;
    }
    if (novaCidadeTrim === cidadeAntiga) return;

    if (todasCidades.some(c => c.toLowerCase() === novaCidadeTrim.toLowerCase())) {
        alert(`A cidade "${novaCidadeTrim}" já está cadastrada.`);
        return;
    }

    todasCidades = todasCidades.map(c => c === cidadeAntiga ? novaCidadeTrim : c);
    todasCidades.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));

    let alterouMotoristas = false;
    if (Array.isArray(motoristasPlataformaModal)) {
        motoristasPlataformaModal.forEach(item => {
            if (item.cidade.toLowerCase() === cidadeAntiga.toLowerCase()) {
                item.cidade = novaCidadeTrim;
                alterouMotoristas = true;
            }
        });
    }

    try {
        const resCid = await fetch(`${API_URL}/salvar-cidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cidades: todasCidades })
        });
        const dataCid = await resCid.json();
        if (dataCid.status !== 'sucesso') throw new Error(dataCid.mensagem);

        if (alterouMotoristas) {
            const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : (platformSelector.value || "anjun");
            const resMot = await fetch(`${API_URL}/salvar-motoristas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motoristas: motoristasPlataformaModal, plataforma: platId })
            });
            const dataMot = await resMot.json();
            if (dataMot.status !== 'sucesso') throw new Error(dataMot.mensagem);
        }

        renderizarListaCidadesModal();
        renderizarListaMotoristasModal();
        await carregarConfiguracoes();
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

window.deletarCidadeModal = async (cidade) => {
    const confirmou = await customConfirm("Excluir Cidade", `Deseja realmente remover a cidade "${cidade}"?\nIsso também removerá todos os mapeamentos de motoristas associados a ela.`);
    if (!confirmou) return;

    todasCidades = todasCidades.filter(c => c.toLowerCase() !== cidade.toLowerCase());

    let alterouMotoristas = false;
    if (Array.isArray(motoristasPlataformaModal)) {
        const antes = motoristasPlataformaModal.length;
        motoristasPlataformaModal = motoristasPlataformaModal.filter(item => item.cidade.toLowerCase() !== cidade.toLowerCase());
        if (motoristasPlataformaModal.length !== antes) alterouMotoristas = true;
    }

    try {
        const resCid = await fetch(`${API_URL}/salvar-cidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cidades: todasCidades })
        });
        const dataCid = await resCid.json();
        if (dataCid.status !== 'sucesso') throw new Error(dataCid.mensagem);

        if (alterouMotoristas) {
            const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : (platformSelector.value || "anjun");
            const resMot = await fetch(`${API_URL}/salvar-motoristas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motoristas: motoristasPlataformaModal, plataforma: platId })
            });
            const dataMot = await resMot.json();
            if (dataMot.status !== 'sucesso') throw new Error(dataMot.mensagem);
        }

        renderizarListaCidadesModal();
        renderizarListaMotoristasModal();
        await carregarConfiguracoes();
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

// ----------------------------------------------------
// ABA MOTORISTAS
// ----------------------------------------------------
function normalizarTextoBuscaModal(str) {
    return String(str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function popularMotoristaPlataformaDropdownModal() {
    if (!motoristaPlataformaSelect) return;
    const ids = Object.keys(todasPlataformas);
    const platAtual = (platformSelector && platformSelector.value) || ids[0] || "anjun";

    motoristaPlataformaSelect.innerHTML = ids.map(id => `
        <option value="${id}">${todasPlataformas[id].nome}</option>
    `).join('');

    if (ids.includes(platAtual)) {
        motoristaPlataformaSelect.value = platAtual;
    }
}

async function carregarMotoristasSiteModal(forcar = false) {
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : ((platformSelector && platformSelector.value) || "anjun");
    if (!platId || !motNomeSelect) return;

    const valorAtual = (motNomeSelect.value && motNomeSelect.value !== '__manual__') ? motNomeSelect.value : '';
    if (forcar && btnAtualizarMotoristasSite) {
        btnAtualizarMotoristasSite.disabled = true;
        btnAtualizarMotoristasSite.innerText = "⏳ Buscando...";
    }

    const platPainel = (platformSelector && platformSelector.value) || plataformaAtiva || '';
    const contaAtivaParam = (platId === platPainel && contaSelecionadaNaSessao && contaSelecionadaNaSessao !== 'padrao')
        ? `&conta_id=${encodeURIComponent(contaSelecionadaNaSessao)}`
        : '';

    try {
        const res = await fetch(`${API_URL}/motoristas/lista-site?plataforma=${encodeURIComponent(platId)}${contaAtivaParam}${forcar ? '&forcar=1' : ''}&_=${Date.now()}`);
        const nomesSet = new Set();
        if (res.ok) {
            const data = await res.json();
            if (Array.isArray(data.motoristas)) {
                data.motoristas.forEach(n => {
                    if (n && String(n).trim()) nomesSet.add(String(n).trim());
                });
            }
        }
        if (Array.isArray(motoristasPlataformaModal)) {
            motoristasPlataformaModal.forEach(item => {
                if (item && item.motorista && String(item.motorista).trim()) {
                    nomesSet.add(String(item.motorista).trim());
                }
            });
        }
        motoristasSiteModalLista = Array.from(nomesSet).sort((a, b) =>
            a.localeCompare(b, 'pt-BR', { sensitivity: 'base' })
        );
        renderizarSelectMotoristasSiteModal(valorAtual);
    } catch (err) {
        console.error("Erro ao carregar lista de motoristas do site:", err);
    } finally {
        if (forcar && btnAtualizarMotoristasSite) {
            btnAtualizarMotoristasSite.disabled = false;
            btnAtualizarMotoristasSite.innerText = "🔄 Atualizar do Site";
        }
    }
}

function renderizarSelectMotoristasSiteModal(valorSelecionar = null) {
    if (!motNomeSelect) return;
    const termo = motBuscaSiteInput ? normalizarTextoBuscaModal(motBuscaSiteInput.value) : '';
    const valorPreservado = valorSelecionar !== null ? valorSelecionar : motNomeSelect.value;

    const filtrados = termo
        ? motoristasSiteModalLista.filter(m => normalizarTextoBuscaModal(m).includes(termo))
        : motoristasSiteModalLista;

    let html = `<option value="">${
        filtrados.length > 0
            ? `Selecione o motorista (${filtrados.length} disponíveis)...`
            : `Nenhum motorista encontrado para "${motBuscaSiteInput ? motBuscaSiteInput.value : ''}"`
    }</option>`;

    html += filtrados.map(m => {
        const escaped = m.replace(/"/g, '&quot;');
        return `<option value="${escaped}">${m}</option>`;
    }).join('');

    html += `<option value="__manual__">✏️ Digitar outro nome manualmente...</option>`;
    motNomeSelect.innerHTML = html;

    if (valorPreservado && (filtrados.includes(valorPreservado) || valorPreservado === '__manual__')) {
        motNomeSelect.value = valorPreservado;
    } else if (termo && filtrados.length > 0) {
        motNomeSelect.value = filtrados[0];
    } else {
        motNomeSelect.value = '';
    }

    atualizarVisibilidadeInputManualMotorista();
}

function atualizarVisibilidadeInputManualMotorista() {
    if (!motNomeSelect || !motNomeManualGroup) return;
    if (motNomeSelect.value === '__manual__') {
        motNomeManualGroup.style.display = 'block';
        if (motNome) motNome.required = true;
    } else {
        motNomeManualGroup.style.display = 'none';
        if (motNome) {
            motNome.required = false;
            motNome.value = motNomeSelect.value || '';
        }
    }
}

if (motNomeSelect) {
    motNomeSelect.addEventListener('change', () => {
        atualizarVisibilidadeInputManualMotorista();
        if (motNomeSelect.value === '__manual__' && motNome) {
            motNome.value = '';
            motNome.focus();
        }
    });
}

if (motBuscaSiteInput) {
    motBuscaSiteInput.addEventListener('input', () => {
        renderizarSelectMotoristasSiteModal();
    });
}

if (btnAtualizarMotoristasSite) {
    btnAtualizarMotoristasSite.addEventListener('click', () => {
        carregarMotoristasSiteModal(true);
    });
}

function cancelarEdicaoMapeamentoModal() {
    indexEdicaoMapeamentoModal = null;
    if (formMotoristaTitulo) {
        formMotoristaTitulo.innerText = "Adicionar Novo Mapeamento";
        formMotoristaTitulo.style.color = "";
    }
    if (btnSalvarMapeamentoMot) {
        btnSalvarMapeamentoMot.innerText = "Salvar Mapeamento";
    }
    if (btnCancelarEdicaoMot) {
        btnCancelarEdicaoMot.style.display = "none";
    }
    if (motBuscaSiteInput) motBuscaSiteInput.value = '';
    renderizarSelectMotoristasSiteModal('');
    if (motNome) motNome.value = '';
    if (motCepInput) motCepInput.value = '';
    renderizarListaMotoristasModal();
}

if (btnCancelarEdicaoMot) {
    btnCancelarEdicaoMot.addEventListener('click', cancelarEdicaoMapeamentoModal);
}

async function atualizarMotoristasPlataformaModal() {
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "";
    if (!platId) return;

    cancelarEdicaoMapeamentoModal();

    const platPainel = (platformSelector && platformSelector.value) || plataformaAtiva || '';
    const contaAtivaParam = (platId === platPainel && contaSelecionadaNaSessao && contaSelecionadaNaSessao !== 'padrao')
        ? `&conta_id=${encodeURIComponent(contaSelecionadaNaSessao)}`
        : '';

    try {
        const res = await fetch(`${API_URL}/configuracoes?plataforma=${platId}${contaAtivaParam}&_=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            motoristasPlataformaModal = normalizarMotoristas(data.motoristas);
            renderizarListaMotoristasModal();
        }
    } catch (err) {
        console.error("Erro ao carregar motoristas no modal:", err);
    }

    await carregarMotoristasSiteModal(false);
}

if (motoristaPlataformaSelect) {
    motoristaPlataformaSelect.addEventListener('change', () => {
        atualizarMotoristasPlataformaModal();
    });
}

if (filtroMapeamentosModal) {
    filtroMapeamentosModal.addEventListener('input', () => {
        if (btnLimparFiltroMapeamentos) {
            btnLimparFiltroMapeamentos.style.display = filtroMapeamentosModal.value.trim() ? 'block' : 'none';
        }
        renderizarListaMotoristasModal();
    });
}

if (btnLimparFiltroMapeamentos) {
    btnLimparFiltroMapeamentos.addEventListener('click', () => {
        if (filtroMapeamentosModal) {
            filtroMapeamentosModal.value = '';
            filtroMapeamentosModal.focus();
        }
        btnLimparFiltroMapeamentos.style.display = 'none';
        renderizarListaMotoristasModal();
    });
}

function renderizarListaMotoristasModal() {
    if (!motoristasListBody) return;

    const itemEmEdicao = (indexEdicaoMapeamentoModal !== null && motoristasPlataformaModal[indexEdicaoMapeamentoModal])
        ? motoristasPlataformaModal[indexEdicaoMapeamentoModal]
        : null;

    motoristasPlataformaModal.sort((a, b) => {
        const compCid = a.cidade.localeCompare(b.cidade, 'pt-BR', { sensitivity: 'base' });
        if (compCid !== 0) return compCid;
        return a.motorista.localeCompare(b.motorista, 'pt-BR', { sensitivity: 'base' });
    });

    if (itemEmEdicao) {
        const novoIdx = motoristasPlataformaModal.indexOf(itemEmEdicao);
        indexEdicaoMapeamentoModal = novoIdx >= 0 ? novoIdx : null;
    }

    const termoFiltro = filtroMapeamentosModal ? normalizarTextoBuscaModal(filtroMapeamentosModal.value) : '';
    const itensComIndice = motoristasPlataformaModal.map((item, idx) => ({ item, origIndex: idx }));
    const itensFiltrados = termoFiltro
        ? itensComIndice.filter(({ item }) =>
            normalizarTextoBuscaModal(item.cidade).includes(termoFiltro) ||
            normalizarTextoBuscaModal(item.motorista).includes(termoFiltro) ||
            normalizarTextoBuscaModal(item.faixa_cep || '').includes(termoFiltro)
        )
        : itensComIndice;

    if (contadorMapeamentosModal) {
        if (termoFiltro) {
            contadorMapeamentosModal.innerText = `${itensFiltrados.length} de ${motoristasPlataformaModal.length}`;
        } else {
            contadorMapeamentosModal.innerText = `${motoristasPlataformaModal.length} registros`;
        }
    }

    if (motoristasPlataformaModal.length === 0) {
        motoristasListBody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #64748b;">Nenhum motorista cadastrado para esta plataforma.</td></tr>';
        return;
    }

    if (itensFiltrados.length === 0) {
        motoristasListBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #64748b;">Nenhum mapeamento encontrado para "${filtroMapeamentosModal.value}".</td></tr>`;
        return;
    }

    motoristasListBody.innerHTML = itensFiltrados.map(({ item, origIndex }) => {
        const emEdicao = indexEdicaoMapeamentoModal === origIndex;
        const bgRow = emEdicao ? 'background: rgba(56, 189, 248, 0.12);' : '';
        const isPlaceholder = ['geral', 'sem cidade'].includes((item.cidade || '').trim().toLowerCase());
        const badgeGeral = isPlaceholder
            ? `<span style="color: #f59e0b; font-weight: 500; font-style: italic;">Sem Cidade</span>`
            : `<span style="font-weight: 600; color: #f8fafc;">${item.cidade}</span>`;
        const cepVal = (item.faixa_cep || '').trim();
        const badgeCep = cepVal
            ? `<span style="display: inline-block; padding: 2px 7px; border-radius: 4px; background: rgba(16, 185, 129, 0.16); border: 1px solid rgba(16, 185, 129, 0.45); color: #34d399; font-size: 0.74rem; font-weight: 700;">${cepVal}</span>`
            : `<span style="color: #64748b; font-size: 0.74rem;">Cidade inteira</span>`;
        return `
            <tr style="${bgRow}">
                <td>${badgeGeral}</td>
                <td style="color: #38bdf8;">${item.motorista}</td>
                <td>${badgeCep}</td>
                <td style="text-align: right; white-space: nowrap; overflow: visible; text-overflow: clip;">
                    <button type="button" class="btn-row-action" style="color: #38bdf8; margin-right: 10px;" onclick="editarMapeamentoModal(${origIndex})">Editar</button>
                    <button type="button" class="btn-row-action" style="color: #ef4444;" onclick="deletarMapeamentoModal(${origIndex})">Deletar</button>
                </td>
            </tr>
        `;
    }).join('');
}

async function salvarMapeamentoMotoristaModal(e) {
    e.preventDefault();
    if (!motCidadeSelect) return;
    const cidade = motCidadeSelect.value.trim();
    const faixaCep = motCepInput ? motCepInput.value.trim() : '';
    const motorista = (motNomeSelect && motNomeSelect.value && motNomeSelect.value !== '__manual__')
        ? motNomeSelect.value.trim()
        : (motNome ? motNome.value.trim() : '');
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : ((platformSelector && platformSelector.value) || plataformaAtiva || "anjun");

    if (!motorista) {
        alert("Selecione o motorista da lista do site (ou digite o nome manualmente).");
        return;
    }
    if (!cidade) {
        alert("Selecione a cidade correspondente para este motorista.");
        return;
    }

    const ehPlaceholder = (c) => ['geral', 'sem cidade'].includes(String(c || '').trim().toLowerCase());
    let acao = 'adicionar';
    let cidadeAntiga = '';
    let motoristaAntigo = '';

    if (indexEdicaoMapeamentoModal !== null && indexEdicaoMapeamentoModal >= 0 && indexEdicaoMapeamentoModal < motoristasPlataformaModal.length) {
        const itemAntigo = motoristasPlataformaModal[indexEdicaoMapeamentoModal];
        cidadeAntiga = itemAntigo.cidade;
        motoristaAntigo = itemAntigo.motorista;
        acao = ehPlaceholder(cidadeAntiga) ? 'adicionar' : 'editar';

        const jaExiste = motoristasPlataformaModal.some((item, idx) =>
            idx !== indexEdicaoMapeamentoModal &&
            item.cidade.toLowerCase() === cidade.toLowerCase() &&
            item.motorista.toLowerCase() === motorista.toLowerCase()
        );
        if (jaExiste) {
            alert(`O motorista "${motorista}" já está cadastrado para a cidade "${cidade}".`);
            return;
        }
        motoristasPlataformaModal[indexEdicaoMapeamentoModal] = { cidade, motorista, faixa_cep: faixaCep };
        if (!ehPlaceholder(cidade)) {
            motoristasPlataformaModal = motoristasPlataformaModal.filter((item, idx) =>
                idx === indexEdicaoMapeamentoModal ||
                !(item.motorista.toLowerCase() === motorista.toLowerCase() && ehPlaceholder(item.cidade))
            );
        }
    } else {
        const idxExistente = motoristasPlataformaModal.findIndex(item =>
            item.cidade.toLowerCase() === cidade.toLowerCase() &&
            item.motorista.toLowerCase() === motorista.toLowerCase()
        );
        if (idxExistente >= 0) {
            // Se já existia naquela cidade e o usuário informou/alterou a faixa de CEP, atualiza!
            if (faixaCep !== (motoristasPlataformaModal[idxExistente].faixa_cep || '')) {
                acao = 'editar';
                cidadeAntiga = motoristasPlataformaModal[idxExistente].cidade;
                motoristaAntigo = motoristasPlataformaModal[idxExistente].motorista;
                motoristasPlataformaModal[idxExistente].faixa_cep = faixaCep;
            } else {
                alert(`O motorista "${motorista}" já está cadastrado para a cidade "${cidade}".`);
                return;
            }
        } else {
            // Se o motorista estava apenas com "Geral" ou "Sem Cidade" provisório, substitui pela cidade escolhida
            if (!ehPlaceholder(cidade)) {
                motoristasPlataformaModal = motoristasPlataformaModal.filter(item =>
                    !(item.motorista.toLowerCase() === motorista.toLowerCase() && ehPlaceholder(item.cidade))
                );
            }
            motoristasPlataformaModal.push({ cidade, motorista, faixa_cep: faixaCep });
        }
    }

    const contaIdAtual = (accountSelector && accountSelector.value && accountSelector.value !== 'padrao')
        ? accountSelector.value
        : (contaSelecionadaNaSessao && contaSelecionadaNaSessao !== 'padrao' ? contaSelecionadaNaSessao : '');

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                acao,
                cidade,
                motorista,
                faixa_cep: faixaCep,
                cidade_antiga: cidadeAntiga,
                motorista_antigo: motoristaAntigo,
                motoristas: motoristasPlataformaModal,
                plataforma: platId,
                conta_id: contaIdAtual
            })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            if (!motoristasSiteModalLista.includes(motorista)) {
                motoristasSiteModalLista.push(motorista);
                motoristasSiteModalLista.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            }
            if (Array.isArray(data.motoristas)) {
                motoristasPlataformaModal = normalizarMotoristas(data.motoristas);
            }
            if (Array.isArray(data.cidades)) {
                todasCidades = data.cidades
                    .map(c => String(c || '').trim())
                    .filter(Boolean)
                    .sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
                renderizarListaCidadesModal();
            }
            if (!plataformaAtiva && (!platformSelector || !platformSelector.value) && platId && todasPlataformas[platId]) {
                plataformaAtiva = platId;
                if (platformSelector) platformSelector.value = platId;
            }
            const platPainel = (platformSelector && platformSelector.value) || plataformaAtiva || platId;
            if (platId.toLowerCase() === platPainel.toLowerCase()) {
                todosMotoristas = [...motoristasPlataformaModal];
                atualizarSeletorMotoristas();
            }
            cancelarEdicaoMapeamentoModal();
            await carregarConfiguracoes();
        } else {
            alert("Erro ao salvar motorista: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
}

if (formMotorista) {
    formMotorista.addEventListener('submit', salvarMapeamentoMotoristaModal);
}

window.editarMapeamentoModal = async (index) => {
    if (index < 0 || index >= motoristasPlataformaModal.length) return;
    const item = motoristasPlataformaModal[index];
    indexEdicaoMapeamentoModal = index;

    if (formMotoristaTitulo) {
        formMotoristaTitulo.innerText = `✏️ Editando: ${item.motorista}`;
        formMotoristaTitulo.style.color = "#38bdf8";
    }
    if (btnSalvarMapeamentoMot) {
        btnSalvarMapeamentoMot.innerText = "Salvar Alteração";
    }
    if (btnCancelarEdicaoMot) {
        btnCancelarEdicaoMot.style.display = "inline-block";
    }

    if (!motoristasSiteModalLista.includes(item.motorista)) {
        motoristasSiteModalLista.push(item.motorista);
        motoristasSiteModalLista.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
    }
    if (motBuscaSiteInput) {
        motBuscaSiteInput.value = '';
    }
    renderizarSelectMotoristasSiteModal(item.motorista);

    if (motCidadeSelect) {
        const opcoesCidades = Array.from(motCidadeSelect.options).map(o => o.value);
        if (item.cidade && !['geral', 'sem cidade'].includes(item.cidade.toLowerCase()) && opcoesCidades.includes(item.cidade)) {
            motCidadeSelect.value = item.cidade;
        } else {
            motCidadeSelect.value = '';
        }
        motCidadeSelect.focus();
    }
    if (motCepInput) {
        motCepInput.value = item.faixa_cep || '';
    }

    renderizarListaMotoristasModal();
};

window.deletarMapeamentoModal = async (index) => {
    if (index < 0 || index >= motoristasPlataformaModal.length) return;
    const item = motoristasPlataformaModal[index];

    const confirmou = await customConfirm("Excluir Motorista", `Deseja remover o motorista "${item.motorista}" da cidade "${item.cidade}"?`);
    if (!confirmou) return;

    if (indexEdicaoMapeamentoModal === index) {
        cancelarEdicaoMapeamentoModal();
    }

    motoristasPlataformaModal.splice(index, 1);
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : ((platformSelector && platformSelector.value) || plataformaAtiva || "anjun");
    const contaIdAtual = (accountSelector && accountSelector.value && accountSelector.value !== 'padrao')
        ? accountSelector.value
        : (contaSelecionadaNaSessao && contaSelecionadaNaSessao !== 'padrao' ? contaSelecionadaNaSessao : '');

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                acao: 'deletar',
                cidade: item.cidade,
                motorista: item.motorista,
                motoristas: motoristasPlataformaModal,
                plataforma: platId,
                conta_id: contaIdAtual
            })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            if (Array.isArray(data.motoristas)) {
                motoristasPlataformaModal = normalizarMotoristas(data.motoristas);
            }
            if (Array.isArray(data.cidades)) {
                todasCidades = data.cidades
                    .map(c => String(c || '').trim())
                    .filter(Boolean)
                    .sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
                renderizarListaCidadesModal();
            }
            const platPainel = (platformSelector && platformSelector.value) || plataformaAtiva || platId;
            if (platId.toLowerCase() === platPainel.toLowerCase()) {
                todosMotoristas = [...motoristasPlataformaModal];
                atualizarSeletorMotoristas();
            }
            renderizarListaMotoristasModal();
            await carregarConfiguracoes();
        } else {
            alert("Erro ao remover motorista: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

// Botões de Planilha Excel (Motoristas_Cidades.xlsx) na Aba Motoristas
const btnAbrirExcelMot = document.getElementById('btn-abrir-excel-mot');
const btnAbrirPastaExcelMot = document.getElementById('btn-abrir-pasta-excel-mot');
const btnSincronizarExcelMot = document.getElementById('btn-sincronizar-excel-mot');
const btnImportarExcelMot = document.getElementById('btn-importar-excel-mot');
const inputImportarExcelMot = document.getElementById('input-importar-excel-mot');

if (btnAbrirExcelMot) {
    btnAbrirExcelMot.addEventListener('click', async () => {
        const txtOrig = btnAbrirExcelMot.innerText;
        btnAbrirExcelMot.disabled = true;
        btnAbrirExcelMot.innerText = "⏳ Abrindo...";
        try {
            const res = await fetch(`${API_URL}/motoristas/abrir-excel`, { method: 'POST' });
            const data = await res.json();
            if (data.status === 'sucesso') {
                alert("Planilha Motoristas_Cidades.xlsx aberta no Excel!\n\nApós editar e salvar o arquivo no Excel, clique em '🔄 Sincronizar'.");
            } else {
                window.open(`${API_URL}/motoristas/exportar-excel`, '_blank');
            }
        } catch (err) {
            window.open(`${API_URL}/motoristas/exportar-excel`, '_blank');
        } finally {
            btnAbrirExcelMot.disabled = false;
            btnAbrirExcelMot.innerText = txtOrig;
        }
    });
}

if (btnAbrirPastaExcelMot) {
    btnAbrirPastaExcelMot.addEventListener('click', async () => {
        const txtOrig = btnAbrirPastaExcelMot.innerText;
        btnAbrirPastaExcelMot.disabled = true;
        btnAbrirPastaExcelMot.innerText = "⏳ Abrindo...";
        try {
            await fetch(`${API_URL}/motoristas/abrir-pasta-excel`, { method: 'POST' });
        } catch (err) {
            console.warn("Erro ao abrir pasta da planilha:", err);
        } finally {
            btnAbrirPastaExcelMot.disabled = false;
            btnAbrirPastaExcelMot.innerText = txtOrig;
        }
    });
}

if (btnSincronizarExcelMot) {
    btnSincronizarExcelMot.addEventListener('click', async () => {
        const txtOrig = btnSincronizarExcelMot.innerText;
        btnSincronizarExcelMot.disabled = true;
        btnSincronizarExcelMot.innerText = "⏳ Sincronizando...";
        try {
            const res = await fetch(`${API_URL}/motoristas/sincronizar-excel`, { method: 'POST' });
            const data = await res.json();
            if (data.status === 'sucesso') {
                await carregarConfiguracoes();
                renderizarListaCidadesModal();
                await atualizarMotoristasPlataformaModal();
                alert("✓ " + (data.mensagem || "Planilha sincronizada com sucesso!"));
            } else {
                alert("Aviso: " + (data.mensagem || "Não foi possível sincronizar a planilha."));
            }
        } catch (err) {
            alert("Erro de conexão ao sincronizar planilha: " + err.message);
        } finally {
            btnSincronizarExcelMot.disabled = false;
            btnSincronizarExcelMot.innerText = txtOrig;
        }
    });
}

if (btnImportarExcelMot && inputImportarExcelMot) {
    btnImportarExcelMot.addEventListener('click', () => {
        inputImportarExcelMot.value = '';
        inputImportarExcelMot.click();
    });

    inputImportarExcelMot.addEventListener('change', async (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;

        const txtOrig = btnImportarExcelMot.innerText;
        btnImportarExcelMot.disabled = true;
        btnImportarExcelMot.innerText = "⏳ Importando...";

        try {
            const formData = new FormData();
            formData.append('planilha', file);

            const res = await fetch(`${API_URL}/motoristas/importar-excel`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.status === 'sucesso') {
                await carregarConfiguracoes();
                renderizarListaCidadesModal();
                await atualizarMotoristasPlataformaModal();
                alert("✓ " + (data.mensagem || "Planilha importada com sucesso!"));
            } else {
                alert("Erro ao importar planilha: " + (data.mensagem || "Formato inválido."));
            }
        } catch (err) {
            alert("Erro ao enviar planilha: " + err.message);
        } finally {
            btnImportarExcelMot.disabled = false;
            btnImportarExcelMot.innerText = txtOrig;
        }
    });
}

// ----------------------------------------------------
// ABA CREDENCIAIS / MÚLTIPLOS LOGINS
// ----------------------------------------------------
const contasPlataformaListBody = document.getElementById('contas-plataforma-list-body');
const modalContaId = document.getElementById('modal-conta-id');
const modalContaApelido = document.getElementById('modal-conta-apelido');
const tituloFormConta = document.getElementById('titulo-form-conta');
const btnNovaContaLimpar = document.getElementById('btn-nova-conta-limpar');
let cacheContasPlataformasModal = {};

function limparFormularioContaModal() {
    if (modalContaId) modalContaId.value = "";
    if (modalContaApelido) modalContaApelido.value = "";
    if (modalLoginUser) modalLoginUser.value = "";
    if (modalLoginPass) modalLoginPass.value = "";
    if (tituloFormConta) tituloFormConta.innerText = "➕ Nova Conta / Login";
    if (btnModalSalvar) btnModalSalvar.innerText = "Salvar Nova Conta";
    if (btnNovaContaLimpar) btnNovaContaLimpar.style.display = "none";
}

if (btnNovaContaLimpar) {
    btnNovaContaLimpar.addEventListener('click', limparFormularioContaModal);
}

async function popularCredenciaisPlataformaModal() {
    if (!modalPlatSelector) return;
    const keys = Object.keys(todasPlataformas);
    if (keys.length === 0) {
        modalPlatSelector.innerHTML = '<option value="">Nenhuma plataforma cadastrada</option>';
        limparFormularioContaModal();
        return;
    }

    modalPlatSelector.innerHTML = keys.map(key => `
        <option value="${key}">${todasPlataformas[key].nome}</option>
    `).join('');

    const platAtual = (platformSelector && platformSelector.value) || plataformaAtiva || keys[0];
    modalPlatSelector.value = platAtual;
    await carregarDadosPlataformaModal(platAtual);
}

async function carregarDadosPlataformaModal(platId) {
    limparFormularioContaModal();
    try {
        const res = await fetch(`${API_URL}/plataformas/contas?_=${Date.now()}`);
        const data = await res.json();
        cacheContasPlataformasModal = (data && data.dados) ? data.dados : (data || {});
    } catch (e) {
        console.warn("Erro ao buscar contas para modal:", e);
    }
    renderizarTabelaContasModal(platId);
}

function renderizarTabelaContasModal(platId) {
    if (!contasPlataformaListBody) return;
    const info = cacheContasPlataformasModal[platId] || { conta_ativa: "", contas: [] };
    const lista = Array.isArray(info.contas) ? info.contas : [];
    const ativaId = info.conta_ativa || (lista[0] ? lista[0].id : "");

    if (lista.length === 0) {
        contasPlataformaListBody.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center; color: #64748b; padding: 16px;">
                    Nenhuma conta cadastrada para esta plataforma. Adicione ao lado!
                </td>
            </tr>
        `;
        return;
    }

    contasPlataformaListBody.innerHTML = lista.map(c => {
        const isAtiva = (c.id === ativaId);
        const idEsc = (c.id || '').replace(/'/g, "\\'");
        return `
            <tr style="${isAtiva ? 'background: rgba(16, 185, 129, 0.08);' : ''}">
                <td style="font-weight: 700; color: #f8fafc;">
                    ${isAtiva ? '<span style="color: #34d399; margin-right: 4px;">🟢</span>' : ''}
                    ${c.apelido || c.login_usuario || 'Conta'}
                </td>
                <td style="font-family: monospace; color: #cbd5e1; font-size: 0.82rem;">${c.login_usuario || '---'}</td>
                <td style="text-align: right; white-space: nowrap;">
                    ${!isAtiva ? `<button type="button" class="btn-row-action" style="color: #34d399; margin-right: 8px;" onclick="ativarContaPeloModal('${idEsc}')">Usar</button>` : `<span style="font-size: 0.7rem; color: #34d399; font-weight: 800; margin-right: 8px;">ATIVA</span>`}
                    <button type="button" class="btn-row-action" style="color: #38bdf8; margin-right: 8px;" onclick="editarContaPeloModal('${idEsc}')">Editar</button>
                    <button type="button" class="btn-row-action" style="color: #ef4444;" onclick="excluirContaPeloModal('${idEsc}')">Excluir</button>
                </td>
            </tr>
        `;
    }).join('');
}

window.editarContaPeloModal = function(contaId) {
    const platId = modalPlatSelector ? modalPlatSelector.value : "";
    const info = cacheContasPlataformasModal[platId];
    if (!info || !Array.isArray(info.contas)) return;
    const conta = info.contas.find(c => c.id === contaId);
    if (!conta) return;

    if (modalContaId) modalContaId.value = conta.id;
    if (modalContaApelido) modalContaApelido.value = conta.apelido || "";
    if (modalLoginUser) modalLoginUser.value = conta.login_usuario || "";
    if (modalLoginPass) modalLoginPass.value = conta.login_senha || "";
    if (tituloFormConta) tituloFormConta.innerText = `✏️ Editando: ${conta.apelido || conta.login_usuario}`;
    if (btnModalSalvar) btnModalSalvar.innerText = "Salvar Alterações";
    if (btnNovaContaLimpar) btnNovaContaLimpar.style.display = "inline-block";
};

window.ativarContaPeloModal = async function(contaId) {
    const platId = modalPlatSelector ? modalPlatSelector.value : "";
    if (!platId || !contaId) return;
    try {
        const res = await fetch(`${API_URL}/plataformas/selecionar-conta`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plataforma: platId, conta_id: contaId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            await carregarDadosPlataformaModal(platId);
            await atualizarSeletorContasPlataforma();
        } else {
            alert("Erro ao ativar conta: " + (data.mensagem || "Erro"));
        }
    } catch (e) {
        alert("Erro ao conectar com o servidor.");
    }
};

window.excluirContaPeloModal = async function(contaId) {
    const platId = modalPlatSelector ? modalPlatSelector.value : "";
    if (!platId || !contaId) return;
    const confirmou = await customConfirm("Excluir Conta", "Deseja realmente excluir esta conta de login?");
    if (!confirmou) return;

    try {
        const res = await fetch(`${API_URL}/plataformas/excluir-conta`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plataforma: platId, id: contaId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            await carregarDadosPlataformaModal(platId);
            await atualizarSeletorContasPlataforma();
        } else {
            alert(data.mensagem || "Não foi possível excluir a conta.");
        }
    } catch (e) {
        alert("Erro ao conectar com o servidor.");
    }
};

if (modalPlatSelector) {
    modalPlatSelector.addEventListener('change', (e) => {
        carregarDadosPlataformaModal(e.target.value);
    });
}

if (btnModalSalvar) {
    btnModalSalvar.addEventListener('click', async () => {
        const platId = modalPlatSelector ? modalPlatSelector.value : "";
        if (!platId) {
            alert("Selecione uma plataforma!");
            return;
        }

        const cId = modalContaId ? modalContaId.value.trim() : "";
        const apelido = modalContaApelido ? modalContaApelido.value.trim() : "";
        const usuario = modalLoginUser ? modalLoginUser.value.trim() : "";
        const senha = modalLoginPass ? modalLoginPass.value.trim() : "";

        if (!usuario) {
            alert("Informe o usuário de login!");
            return;
        }

        const payload = {
            plataforma: platId,
            id: cId,
            apelido: apelido || usuario,
            login_usuario: usuario,
            login_senha: senha,
            ativar_agora: false
        };

        btnModalSalvar.disabled = true;
        btnModalSalvar.innerText = "Salvando...";

        try {
            const res = await fetch(`${API_URL}/plataformas/salvar-conta`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'sucesso') {
                await carregarDadosPlataformaModal(platId);
                await atualizarSeletorContasPlataforma();
            } else {
                alert("Erro ao salvar: " + data.mensagem);
            }
        } catch (e) {
            console.error(e);
            alert("Erro ao conectar com o servidor.");
        } finally {
            btnModalSalvar.disabled = false;
            btnModalSalvar.innerText = "Salvar Nova Conta";
        }
    });
}

// Event listener para cópia rápida de códigos clicando nas tabelas
document.addEventListener('click', (e) => {
    if (e.target && e.target.classList.contains('copyable-code')) {
        const text = e.target.innerText.trim();
        if (text === 'Copiado!') return;
        navigator.clipboard.writeText(text).then(() => {
            const originalBg = e.target.style.background;
            const originalColor = e.target.style.color;
            const originalText = e.target.innerText;
            e.target.style.background = '#22c55e';
            e.target.style.color = '#fff';
            e.target.style.borderRadius = '4px';
            e.target.style.padding = '2px 6px';
            e.target.innerText = 'Copiado!';
            setTimeout(() => {
                e.target.style.background = originalBg;
                e.target.style.color = originalColor;
                e.target.style.borderRadius = '';
                e.target.style.padding = '';
                e.target.innerText = originalText;
            }, 800);
        }).catch(err => {
            console.error('Falha ao copiar:', err);
        });
    }
});

// ========================================================
// FILTRO EM TEMPO REAL - ÚLTIMAS MOVIMENTAÇÕES
// ========================================================
const filtroHistoricoInput = document.getElementById('filtro-historico-input');
const btnLimparFiltroHistorico = document.getElementById('btn-limpar-filtro-historico');
const btnFiltroApenasDuplicados = document.getElementById('btn-filtro-apenas-duplicados');
const filtroHistoricoCount = document.getElementById('filtro-historico-count');
let filtroApenasDuplicadosAtivo = false;

function normalizarTextoBusca(str) {
    return String(str || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

function filtrarTabelaHistorico() {
    if (!historyLog) return;
    const termo = normalizarTextoBusca(filtroHistoricoInput ? filtroHistoricoInput.value : "");
    const linhas = historyLog.querySelectorAll('tr');
    let encontrados = 0;
    
    if (btnLimparFiltroHistorico) {
        btnLimparFiltroHistorico.style.display = (termo || filtroApenasDuplicadosAtivo) ? 'block' : 'none';
    }
    
    linhas.forEach(linha => {
        const textoLinha = normalizarTextoBusca(linha.innerText);
        const ehDuplicado = textoLinha.includes('duplicado') || textoLinha.includes('reatribuido');
        
        let matchTermo = !termo || textoLinha.includes(termo);
        let matchDuplicado = !filtroApenasDuplicadosAtivo || ehDuplicado;
        
        if (matchTermo && matchDuplicado) {
            linha.style.display = '';
            encontrados++;
            if (termo && termo.length >= 3) {
                linha.classList.add('linha-destacada');
            } else {
                linha.classList.remove('linha-destacada');
            }
        } else {
            linha.style.display = 'none';
            linha.classList.remove('linha-destacada');
        }
    });
    
    if (filtroHistoricoCount) {
        if (termo || filtroApenasDuplicadosAtivo) {
            filtroHistoricoCount.innerText = `${encontrados} ${encontrados === 1 ? 'resultado' : 'resultados'}`;
            filtroHistoricoCount.style.display = 'inline-block';
            filtroHistoricoCount.style.color = encontrados > 0 ? '#38bdf8' : '#f87171';
        } else {
            filtroHistoricoCount.style.display = 'none';
        }
    }
}

window.filtrarPorCodigoHistorico = function(codigo) {
    if (!codigo) return;
    filtroApenasDuplicadosAtivo = false;
    if (btnFiltroApenasDuplicados) {
        btnFiltroApenasDuplicados.style.background = 'rgba(239, 68, 68, 0.12)';
        btnFiltroApenasDuplicados.style.borderColor = 'rgba(239, 68, 68, 0.35)';
        btnFiltroApenasDuplicados.style.color = '#f87171';
    }
    if (filtroHistoricoInput) {
        filtroHistoricoInput.value = codigo.trim();
        filtrarTabelaHistorico();
        filtroHistoricoInput.focus();
        filtroHistoricoInput.select();
    }
};

if (filtroHistoricoInput) {
    filtroHistoricoInput.addEventListener('input', () => {
        filtrarTabelaHistorico();
    });
    filtroHistoricoInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            filtroHistoricoInput.value = '';
            filtroApenasDuplicadosAtivo = false;
            filtrarTabelaHistorico();
            if (input) input.focus();
        } else if (e.key === 'Enter') {
            if (input) input.focus();
        }
    });
}

if (btnLimparFiltroHistorico) {
    btnLimparFiltroHistorico.addEventListener('click', () => {
        if (filtroHistoricoInput) filtroHistoricoInput.value = '';
        filtroApenasDuplicadosAtivo = false;
        if (btnFiltroApenasDuplicados) {
            btnFiltroApenasDuplicados.style.background = 'rgba(239, 68, 68, 0.12)';
            btnFiltroApenasDuplicados.style.borderColor = 'rgba(239, 68, 68, 0.35)';
            btnFiltroApenasDuplicados.style.color = '#f87171';
        }
        filtrarTabelaHistorico();
        if (input) input.focus();
    });
}

if (btnFiltroApenasDuplicados) {
    btnFiltroApenasDuplicados.addEventListener('click', () => {
        filtroApenasDuplicadosAtivo = !filtroApenasDuplicadosAtivo;
        if (filtroApenasDuplicadosAtivo) {
            btnFiltroApenasDuplicados.style.background = '#dc2626';
            btnFiltroApenasDuplicados.style.borderColor = '#ef4444';
            btnFiltroApenasDuplicados.style.color = '#ffffff';
        } else {
            btnFiltroApenasDuplicados.style.background = 'rgba(239, 68, 68, 0.12)';
            btnFiltroApenasDuplicados.style.borderColor = 'rgba(239, 68, 68, 0.35)';
            btnFiltroApenasDuplicados.style.color = '#f87171';
        }
        filtrarTabelaHistorico();
    });
}

// Função auxiliar para obter a data local no formato YYYY-MM-DD
function obterDataHojeLocal() {
    const d = new Date();
    const ano = d.getFullYear();
    const mes = String(d.getMonth() + 1).padStart(2, '0');
    const dia = String(d.getDate()).padStart(2, '0');
    return `${ano}-${mes}-${dia}`;
}

// Função para atualizar os dados de bipes e lotes finalizados por data / período
async function atualizarFechamentoData(dataInicio, dataFim) {
    if (!dataInicio) dataInicio = obterDataHojeLocal();
    if (!dataFim) dataFim = dataInicio;
    
    // 1. Carregar lotes finalizados para essa data / período
    try {
        const res = await fetch(`${API_URL}/atribuicao/lotes-finalizados?data_inicio=${dataInicio}&data_fim=${dataFim}&_=${Date.now()}`);
        if (res.ok) {
            lotesFinalizadosCarregados = await res.json();
            aplicarOrdenacaoERenderizar();
        }
    } catch (e) {
        console.error("Erro ao carregar lotes do período:", e);
    }
    
    // 2. Carregar histórico detalhado para essa data / período
    try {
        const res = await fetch(`${API_URL}/historico?data_inicio=${dataInicio}&data_fim=${dataFim}&_=${Date.now()}`);
        if (res.ok) {
            const histData = await res.json();
            historyLog.innerHTML = "";
            const bipsOk = histData.filter(b => b.status === "OK");
            recalcularContagemEmpresas(bipsOk, lotesFinalizadosCarregados);
            const ehHoje = (dataInicio === obterDataHojeLocal() && dataFim === obterDataHojeLocal());
            reconstruirDuplicadosDoHistorico(histData, ehHoje);
            if (histData.length > 0) {
                const ultimo = histData[histData.length - 1];
                atualizarCardUltimoPacote(
                    ultimo.codigo || '---',
                    ultimo.cidade || '---',
                    ultimo.motorista || '---',
                    ultimo.status === 'OK' ? 'PROCESSADO' : (ultimo.status || 'ERRO'),
                    ultimo.status === 'OK'
                );
            }
            
            // Renderiza os bips dessa data (todos, ordenados de forma decrescente por horário)
            const bipsExibidos = [...histData].reverse();
            bipsExibidos.forEach(bip => {
                const badgeClass = bip.status === "OK" ? "badge-ok" : "badge-err";
                const statusText = bip.status;
                
                let horarioStr = "---";
                if (bip.timestamp) {
                    if (bip.timestamp.includes("T")) {
                        const partes = bip.timestamp.split("T");
                        const dataPart = partes[0].substring(5); // MM-DD
                        const horaPart = partes[1].substring(0, 5); // HH:MM
                        horarioStr = `${dataPart} ${horaPart}`;
                    } else {
                        horarioStr = bip.timestamp;
                    }
                }
                
                const novaLinha = document.createElement('tr');
                const statusSafe = String(statusText || '').replace(/"/g, '&quot;');
                const codEscaped = String(bip.codigo || '').replace(/'/g, "\\'");
                novaLinha.innerHTML = `
                    <td style="color: #64748b;">${horarioStr}</td>
                    <td style="font-family: monospace; white-space: nowrap;">
                        <span class="copyable-code" style="cursor: pointer; transition: all 0.2s;" title="Clique para copiar (${bip.codigo})">${bip.codigo}</span>
                        <span class="btn-filtrar-pacote" onclick="filtrarPorCodigoHistorico('${codEscaped}')" title="🔍 Filtrar todas as movimentações deste pacote (${bip.codigo})" style="cursor: pointer; opacity: 0.6; padding: 1px 4px; border-radius: 3px; font-size: 0.72rem; margin-left: 6px;">🔍</span>
                    </td>
                    <td title="${bip.cidade}">${bip.cidade}</td>
                    <td style="text-align: center;" title="${statusSafe}"><span class="status-badge ${badgeClass}" title="${statusSafe}" style="cursor: help;">${statusText}</span></td>
                `;
                historyLog.appendChild(novaLinha);
            });

            if (typeof filtrarTabelaHistorico === 'function') {
                const inputFiltro = document.getElementById('filtro-historico-input');
                if (inputFiltro && (inputFiltro.value.trim() || filtroApenasDuplicadosAtivo)) {
                    filtrarTabelaHistorico();
                }
            }
        }
    } catch (e) {
        console.error("Erro ao carregar histórico do período:", e);
    }
}

// Função auxiliar para processar bipes inseridos manualmente
function processarCodigoManual(codigo) {
    if (sistemaTravado) {
        alert("O sistema está travado por divergência. Destrave antes de processar outro bipe.");
        if (input) input.focus();
        return;
    }
    codigo = codigo.trim();
    if (!codigo) {
        if (input) input.focus();
        return;
    }

    // Se estiver visualizando outra data, volta para "Hoje" ao bipar
    const filterDateStart = document.getElementById('filter-date-start');
    const filterDateEnd = document.getElementById('filter-date-end');
    const hojeLocal = obterDataHojeLocal();
    if ((filterDateStart && filterDateStart.value !== hojeLocal) || (filterDateEnd && filterDateEnd.value !== hojeLocal)) {
        if (filterDateStart) filterDateStart.value = hojeLocal;
        if (filterDateEnd) filterDateEnd.value = hojeLocal;
        atualizarFechamentoData(hojeLocal, hojeLocal);
    }

    const platSelecionada = platformSelector.value;
    if (!platSelecionada) {
        alert("Nenhuma plataforma está selecionada.");
        if (input) input.focus();
        return;
    }

    let motoristaLote = driverSelect.value || null;
    let cidadesParaEnviar = [];
    if (platSelecionada === 'loggi') {
        cidadesParaEnviar = [...cidadesLoggiSelecionadas];
        motoristaLote = cidadesParaEnviar.length > 0 ? cidadesParaEnviar[0] : null;
    }

    // Adiciona o bipe à fila de processamento e salva no localStorage
    filaBipes.push({ 
        codigo: codigo, 
        plataforma: platSelecionada, 
        motorista: motoristaLote,
        cidades_selecionadas: cidadesParaEnviar,
        pacote_solto: (platSelecionada === 'imile' && pacoteSoltoAtivo)
    });
    salvarFilaNoLocalStorage();

    // Inicia o processamento caso a fila esteja ociosa
    if (!processandoFila) {
        processarProximoDaFila();
    } else {
        const filaRestante = filaBipes.length - 1;
        subStatusLabel.innerText = `Processando anterior... [Fila: ${filaRestante} pendente(s)]`;
    }
    
    // Devolve o foco para o leitor de QR Code principal
    setTimeout(() => {
        if (input) input.focus();
    }, 100);
}

// Configuração dos eventos de input manual
const manualInput = document.getElementById('manual-code-input');
const btnManualEnviar = document.getElementById('btn-manual-enviar');

if (manualInput && btnManualEnviar) {
    manualInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const val = manualInput.value.trim();
            if (val) {
                processarCodigoManual(val);
                manualInput.value = '';
            }
        }
    });

    btnManualEnviar.addEventListener('click', () => {
        const val = manualInput.value.trim();
        if (val) {
            processarCodigoManual(val);
            manualInput.value = '';
            if (input) input.focus();
        }
    });
}

// Ao clicar no painel de status ("AGUARDANDO BIP"), foca o leitor principal imediatamente
if (statusPanel) {
    statusPanel.addEventListener('click', (e) => {
        if (!e.target.closest('#manual-input-container')) {
            if (input) input.focus();
        }
    });
}

// Configuração da barra de fechamento por data/período e exportação
const filterDateStart = document.getElementById('filter-date-start');
const filterDateEnd = document.getElementById('filter-date-end');
const btnExportarCSV = document.getElementById('btn-exportar-csv');

function handlePeriodoChange() {
    const start = filterDateStart ? filterDateStart.value : obterDataHojeLocal();
    const end = filterDateEnd ? filterDateEnd.value : start;
    atualizarFechamentoData(start, end);
}

if (filterDateStart) {
    filterDateStart.value = obterDataHojeLocal();
    filterDateStart.addEventListener('change', handlePeriodoChange);
}

if (filterDateEnd) {
    filterDateEnd.value = obterDataHojeLocal();
    filterDateEnd.addEventListener('change', handlePeriodoChange);
}

if (btnExportarCSV) {
    btnExportarCSV.addEventListener('click', () => {
        const start = filterDateStart ? filterDateStart.value : obterDataHojeLocal();
        const end = filterDateEnd ? filterDateEnd.value : start;
        window.open(`${API_URL}/atribuicao/exportar-csv?data_inicio=${start}&data_fim=${end}`, '_blank');
    });
}

// --- REINICIALIZAÇÃO DO SISTEMA E DO SERVIDOR (RESET GERAL) ---
const btnReiniciarSistema = document.getElementById('btn-reiniciar-sistema');
const overlayReiniciando = document.getElementById('overlay-reiniciando');
const overlayReiniciandoMsg = document.getElementById('overlay-reiniciando-msg');

if (btnReiniciarSistema) {
    btnReiniciarSistema.addEventListener('click', async () => {
        if (overlayReiniciando) {
            overlayReiniciando.style.display = 'flex';
        }
        if (overlayReiniciandoMsg) {
            overlayReiniciandoMsg.innerText = "Reiniciando o servidor e reconectando...";
        }

        try {
            await fetch(`${API_URL}/reiniciar-sistema`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (e) {
            console.log("[*] Servidor finalizando para reinício...");
        }

        // Aguarda 1.5s para o processo antigo encerrar e novo iniciar
        await new Promise(r => setTimeout(r, 1500));

        let tentativas = 0;
        const maxTentativas = 25;
        const intervaloReconexao = setInterval(async () => {
            tentativas++;
            try {
                const res = await fetch(`${API_URL}/ping?_=${Date.now()}`, { cache: 'no-store' });
                if (res.ok) {
                    clearInterval(intervaloReconexao);
                    if (overlayReiniciandoMsg) {
                        overlayReiniciandoMsg.innerText = "Servidor reiniciado com sucesso! Recarregando tela...";
                    }
                    setTimeout(() => {
                        window.location.reload();
                    }, 300);
                }
            } catch (err) {
                if (overlayReiniciandoMsg) {
                    overlayReiniciandoMsg.innerText = `Reiniciando o sistema e reconectando (${tentativas}s)...`;
                }
            }

            if (tentativas >= maxTentativas) {
                clearInterval(intervaloReconexao);
                window.location.reload();
            }
        }, 800);
    });
}

// ========================================================
// SISTEMA DE LICENCIAMENTO & PROTEÇÃO DE MÁQUINA (HWID)
// ========================================================

const modalLicenca = document.getElementById('modal-licenca');
const btnFecharModalLicenca = document.getElementById('btn-fechar-modal-licenca');
const btnStatusLicenca = document.getElementById('btn-status-licenca');
const iconeStatusLicenca = document.getElementById('icone-status-licenca');
const textoStatusLicenca = document.getElementById('texto-status-licenca');
const licencaStatusBanner = document.getElementById('licenca-status-banner');
const licencaStatusIcon = document.getElementById('licenca-status-icon');
const licencaStatusTitulo = document.getElementById('licenca-status-titulo');
const licencaStatusDesc = document.getElementById('licenca-status-desc');
const inputHwidDisplay = document.getElementById('input-hwid-display');
const btnCopiarHwid = document.getElementById('btn-copiar-hwid');
const inputChaveLicenca = document.getElementById('input-chave-licenca');
const btnAtivarLicenca = document.getElementById('btn-ativar-licenca');
const feedbackAtivacaoMsg = document.getElementById('feedback-ativacao-msg');
const infoLicencaAtivaBox = document.getElementById('info-licenca-ativa-box');
const infoLicencaCliente = document.getElementById('info-licenca-cliente');
const infoLicencaExpiracao = document.getElementById('info-licenca-expiracao');
const infoLicencaDias = document.getElementById('info-licenca-dias');

let dadosLicencaAtual = null;

async function checarStatusLicenca(forcar = false) {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const url = `${API_URL}/status-licenca?${forcar ? 'forcar=1&' : ''}_=${Date.now()}`;
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!res.ok) return null;
        const lic = await res.json();
        dadosLicencaAtual = lic;
        atualizarInterfaceLicenca(lic);
        return lic;
    } catch (err) {
        console.warn("[Licença] Não foi possível verificar licença:", err);
        return null;
    }
}

function atualizarInterfaceLicenca(lic) {
    if (!lic) return;

    if (inputHwidDisplay && lic.hwid_maquina) {
        inputHwidDisplay.value = lic.hwid_maquina;
    }

    // Atualiza elementos da Aba 4 (Sistema & Nuvem)
    const tabSistemaHwid = document.getElementById('tab-sistema-hwid');
    const tabSistemaStatusLicenca = document.getElementById('tab-sistema-status-licenca');
    if (tabSistemaHwid && lic.hwid_maquina) {
        tabSistemaHwid.innerText = `HWID: ${lic.hwid_maquina}`;
    }

    if (lic.valido) {
        // Licença ativa e regular
        if (tabSistemaStatusLicenca) {
            tabSistemaStatusLicenca.innerText = "ATIVA";
            tabSistemaStatusLicenca.style.background = "rgba(34, 197, 94, 0.15)";
            tabSistemaStatusLicenca.style.border = "1px solid #22c55e";
            tabSistemaStatusLicenca.style.color = "#4ade80";
        }

        // Formatação inteligente e profissional do status da licença
        let textoLic = "LICENÇA ATIVA";
        let iconeLic = "🟢";
        if (lic.dias_restantes > 365) {
            textoLic = "LICENÇA ATIVA";
            iconeLic = "🟢";
        } else if (lic.dias_restantes <= 5) {
            textoLic = `EXPIRA EM ${lic.dias_restantes}D`;
            iconeLic = "🟡";
        } else {
            textoLic = `LICENÇA (${lic.dias_restantes} DIAS)`;
            iconeLic = "🟢";
        }

        if (iconeStatusLicenca) iconeStatusLicenca.innerText = iconeLic;
        if (textoStatusLicenca) textoStatusLicenca.innerText = textoLic;
        if (btnStatusLicenca) {
            btnStatusLicenca.style.display = 'inline-flex';
            btnStatusLicenca.classList.remove('licenca-alerta');
            if (lic.dias_restantes <= 5) {
                btnStatusLicenca.style.borderColor = "#f59e0b";
                btnStatusLicenca.style.color = "#fbbf24";
                btnStatusLicenca.style.background = "rgba(245, 158, 11, 0.15)";
            } else {
                btnStatusLicenca.style.borderColor = "#10b981";
                btnStatusLicenca.style.color = "#34d399";
                btnStatusLicenca.style.background = "rgba(16, 185, 129, 0.15)";
            }
            const platsAtivas = Array.isArray(lic.plataformas_liberadas) && lic.plataformas_liberadas.length > 0
                ? lic.plataformas_liberadas.filter(p => String(p).toLowerCase() !== 'magalog').map(p => p.toUpperCase()).join(', ')
                : 'ANJUN, IMILE, LOGGI';
            btnStatusLicenca.title = `Licença: ${lic.cliente || 'Comercial'} | Empresas: ${platsAtivas} (Válida até ${lic.expiracao}). Clique para detalhes.`;
        }

        if (licencaStatusBanner) {
            licencaStatusBanner.className = "banner-bloqueio banner-ok";
        }
        if (licencaStatusIcon) licencaStatusIcon.innerText = "✓";
        if (licencaStatusTitulo) licencaStatusTitulo.innerText = "LICENÇA ATIVA E REGULAR";
        if (licencaStatusDesc) licencaStatusDesc.innerText = `Sistema autorizado para ${lic.cliente} até ${lic.expiracao}.`;

        if (infoLicencaAtivaBox) infoLicencaAtivaBox.style.display = 'block';
        if (infoLicencaCliente) infoLicencaCliente.innerText = lic.cliente || "---";
        if (infoLicencaExpiracao) infoLicencaExpiracao.innerText = lic.expiracao || "---";
        if (infoLicencaDias) infoLicencaDias.innerText = `${lic.dias_restantes} dias`;

        const liberadasSet = new Set((lic.plataformas_liberadas || ['anjun', 'imile', 'loggi']).map(p => String(p).toLowerCase()));
        document.querySelectorAll('.chk-plat-licenca-local').forEach(chk => {
            chk.checked = liberadasSet.has(chk.value.toLowerCase());
        });

        if (btnFecharModalLicenca) btnFecharModalLicenca.style.display = 'block';
        if (modalLicenca && lic.valido && !window._modalLicencaAbertoManual) {
            modalLicenca.style.display = 'none';
        }

        // Reabilita controles de triagem caso estivessem bloqueados
        if (typeof manualInput !== 'undefined' && manualInput) manualInput.disabled = false;
        if (typeof btnManualEnviar !== 'undefined' && btnManualEnviar) btnManualEnviar.disabled = false;

    } else {
        // Licença inválida, expirada ou não encontrada -> BLOQUEIO
        if (tabSistemaStatusLicenca) {
            tabSistemaStatusLicenca.innerText = lic.codigo === 'EXPIRADA' ? "EXPIRADA" : "BLOQUEADA";
            tabSistemaStatusLicenca.style.background = "rgba(239, 68, 68, 0.15)";
            tabSistemaStatusLicenca.style.border = "1px solid #ef4444";
            tabSistemaStatusLicenca.style.color = "#f87171";
        }

        if (iconeStatusLicenca) iconeStatusLicenca.innerText = "🔴";
        if (textoStatusLicenca) textoStatusLicenca.innerText = "BLOQUEADO";
        if (btnStatusLicenca) {
            btnStatusLicenca.style.display = 'inline-flex';
            btnStatusLicenca.classList.add('licenca-alerta');
            btnStatusLicenca.title = `Atenção: ${lic.motivo}`;
        }

        if (licencaStatusBanner) {
            licencaStatusBanner.className = "banner-bloqueio";
        }
        if (licencaStatusIcon) licencaStatusIcon.innerText = "⚠️";
        if (licencaStatusTitulo) licencaStatusTitulo.innerText = lic.codigo === 'EXPIRADA' ? "MENSALIDADE EXPIRADA" : "SISTEMA BLOQUEADO";
        if (licencaStatusDesc) licencaStatusDesc.innerText = lic.motivo || "Ativação necessária.";

        if (infoLicencaAtivaBox) infoLicencaAtivaBox.style.display = 'none';
        if (btnFecharModalLicenca) btnFecharModalLicenca.style.display = 'none';

        // Abre o modal de bloqueio na tela (não pode fechar)
        if (modalLicenca) {
            modalLicenca.style.display = 'flex';
            carregarCobrancaPix();
        }

        // Trava inputs de triagem
        if (typeof manualInput !== 'undefined' && manualInput) manualInput.disabled = true;
        if (typeof btnManualEnviar !== 'undefined' && btnManualEnviar) btnManualEnviar.disabled = true;
    }
}

// Botão para salvar empresas contratadas diretamente no modal de licença da máquina
const btnSalvarPlatsLicencaLocal = document.getElementById('btn-salvar-plats-licenca-local');
if (btnSalvarPlatsLicencaLocal) {
    btnSalvarPlatsLicencaLocal.addEventListener('click', async () => {
        const selecionadas = Array.from(document.querySelectorAll('.chk-plat-licenca-local:checked')).map(c => c.value);
        if (selecionadas.length === 0) {
            alert("Selecione pelo menos 1 empresa (Anjun, iMile, Loggi ou Magalog) para liberar nesta máquina.");
            return;
        }
        const txtOrig = btnSalvarPlatsLicencaLocal.innerText;
        btnSalvarPlatsLicencaLocal.disabled = true;
        btnSalvarPlatsLicencaLocal.innerText = "⏳ Aplicando empresas...";
        try {
            const res = await fetch(`${API_URL}/licenca/plataformas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ plataformas: selecionadas })
            });
            const data = await res.json();
            if (res.ok && data.sucesso) {
                dadosLicencaAtual = data.status;
                await carregarConfiguracoes();
                btnSalvarPlatsLicencaLocal.innerText = "✓ Empresas Atualizadas!";
                btnSalvarPlatsLicencaLocal.style.background = "#059669";
                setTimeout(() => {
                    btnSalvarPlatsLicencaLocal.innerText = txtOrig;
                    btnSalvarPlatsLicencaLocal.style.background = "linear-gradient(135deg, #0284c7, #0369a1)";
                }, 1800);
            } else {
                alert(data.mensagem || "Erro ao atualizar empresas da licença.");
                btnSalvarPlatsLicencaLocal.innerText = txtOrig;
            }
        } catch (err) {
            alert("Erro de conexão: " + err.message);
            btnSalvarPlatsLicencaLocal.innerText = txtOrig;
        } finally {
            btnSalvarPlatsLicencaLocal.disabled = false;
        }
    });
}

// Botão para abrir o modal de licença manualmente pelo topo
if (btnStatusLicenca) {
    btnStatusLicenca.addEventListener('click', () => {
        if (modalLicenca) {
            window._modalLicencaAbertoManual = true;
            modalLicenca.style.display = 'flex';
            carregarCobrancaPix();
            if (dadosLicencaAtual && dadosLicencaAtual.valido) {
                if (btnFecharModalLicenca) btnFecharModalLicenca.style.display = 'block';
            }
        }
    });
}

// Botão fechar modal (só funciona se a licença estiver válida)
if (btnFecharModalLicenca) {
    btnFecharModalLicenca.addEventListener('click', () => {
        if (dadosLicencaAtual && dadosLicencaAtual.valido) {
            window._modalLicencaAbertoManual = false;
            if (modalLicenca) modalLicenca.style.display = 'none';
        }
    });
}

// Copiar HWID com feedback
if (btnCopiarHwid) {
    btnCopiarHwid.addEventListener('click', async () => {
        if (!inputHwidDisplay || !inputHwidDisplay.value) return;
        try {
            await navigator.clipboard.writeText(inputHwidDisplay.value);
            const originalText = btnCopiarHwid.innerText;
            btnCopiarHwid.innerText = "✓ COPIADO!";
            btnCopiarHwid.style.background = "#059669";
            btnCopiarHwid.style.borderColor = "#10b981";
            btnCopiarHwid.style.color = "#fff";
            setTimeout(() => {
                btnCopiarHwid.innerText = originalText;
                btnCopiarHwid.style.background = "";
                btnCopiarHwid.style.borderColor = "";
                btnCopiarHwid.style.color = "";
            }, 2000);
        } catch (err) {
            inputHwidDisplay.select();
            document.execCommand('copy');
            alert("ID copiado para a área de transferência!");
        }
    });
}

// Ativar chave inserida
if (btnAtivarLicenca) {
    btnAtivarLicenca.addEventListener('click', async () => {
        const chave = inputChaveLicenca ? inputChaveLicenca.value.trim() : "";
        if (!chave) {
            if (feedbackAtivacaoMsg) {
                feedbackAtivacaoMsg.style.display = 'block';
                feedbackAtivacaoMsg.style.background = 'rgba(239, 68, 68, 0.2)';
                feedbackAtivacaoMsg.style.color = '#f87171';
                feedbackAtivacaoMsg.innerText = "Por favor, cole a chave de ativação no campo acima.";
            }
            return;
        }

        btnAtivarLicenca.disabled = true;
        btnAtivarLicenca.innerText = "⏳ Validando Chave...";

        try {
            const res = await fetch(`${API_URL}/ativar-licenca`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chave })
            });
            const data = await res.json();

            if (data.sucesso) {
                if (feedbackAtivacaoMsg) {
                    feedbackAtivacaoMsg.style.display = 'block';
                    feedbackAtivacaoMsg.style.background = 'rgba(16, 185, 129, 0.2)';
                    feedbackAtivacaoMsg.style.color = '#4ade80';
                    feedbackAtivacaoMsg.innerText = "✓ " + data.mensagem;
                }
                atualizarInterfaceLicenca(data.status);
                dadosLicencaAtual = data.status;
                await carregarConfiguracoes();

                setTimeout(() => {
                    window._modalLicencaAbertoManual = false;
                    if (modalLicenca) modalLicenca.style.display = 'none';
                    if (feedbackAtivacaoMsg) feedbackAtivacaoMsg.style.display = 'none';
                    if (inputChaveLicenca) inputChaveLicenca.value = "";
                }, 1500);
            } else {
                if (data.status) {
                    dadosLicencaAtual = data.status;
                    atualizarInterfaceLicenca(data.status);
                }
                if (feedbackAtivacaoMsg) {
                    feedbackAtivacaoMsg.style.display = 'block';
                    feedbackAtivacaoMsg.style.background = 'rgba(239, 68, 68, 0.2)';
                    feedbackAtivacaoMsg.style.color = '#f87171';
                    feedbackAtivacaoMsg.innerText = "✕ " + (data.mensagem || "Chave inválida!");
                }
                await carregarCobrancaPix();
            }
        } catch (err) {
            if (feedbackAtivacaoMsg) {
                feedbackAtivacaoMsg.style.display = 'block';
                feedbackAtivacaoMsg.style.background = 'rgba(239, 68, 68, 0.2)';
                feedbackAtivacaoMsg.style.color = '#f87171';
                feedbackAtivacaoMsg.innerText = "Erro de conexão ao validar chave: " + err.message;
            }
        } finally {
            btnAtivarLicenca.disabled = false;
            btnAtivarLicenca.innerText = "🔓 ATIVAR / RENOVAR SISTEMA";
        }
    });
}


// Controles de PIX e QR Code no Modal de Licença
const tabBtnPix = document.getElementById('tab-btn-pix');
const tabBtnChave = document.getElementById('tab-btn-chave');
const areaAtivacaoPix = document.getElementById('area-ativacao-pix');
const areaAtivacaoManual = document.getElementById('area-ativacao-manual');
const imgPixQrcode = document.getElementById('img-pix-qrcode');
const pixQrLoading = document.getElementById('pix-qr-loading');
const inputPixCopiaCola = document.getElementById('input-pix-copia-cola');
const btnCopiarPixCopiaCola = document.getElementById('btn-copiar-pix-copia-cola');
const btnVerificarPix = document.getElementById('btn-verificar-pix');
const feedbackPixMsg = document.getElementById('feedback-pix-msg');
const pixValorDisplay = document.getElementById('pix-valor-display');
const pixBeneficiarioDisplay = document.getElementById('pix-beneficiario-display');
const pixChaveDisplay = document.getElementById('pix-chave-display');

let dadosCobrancaPix = null;

if (tabBtnPix && tabBtnChave) {
    tabBtnPix.addEventListener('click', () => {
        tabBtnPix.classList.add('active');
        tabBtnPix.style.border = '1px solid #0284c7';
        tabBtnPix.style.background = 'rgba(2, 132, 199, 0.2)';
        tabBtnPix.style.color = '#38bdf8';

        tabBtnChave.classList.remove('active');
        tabBtnChave.style.border = '1px solid #334155';
        tabBtnChave.style.background = '#141822';
        tabBtnChave.style.color = '#94a3b8';

        if (areaAtivacaoPix) areaAtivacaoPix.style.display = 'flex';
        if (areaAtivacaoManual) areaAtivacaoManual.style.display = 'none';
        carregarCobrancaPix();
    });

    tabBtnChave.addEventListener('click', () => {
        tabBtnChave.classList.add('active');
        tabBtnChave.style.border = '1px solid #0284c7';
        tabBtnChave.style.background = 'rgba(2, 132, 199, 0.2)';
        tabBtnChave.style.color = '#38bdf8';

        tabBtnPix.classList.remove('active');
        tabBtnPix.style.border = '1px solid #334155';
        tabBtnPix.style.background = '#141822';
        tabBtnPix.style.color = '#94a3b8';

        if (areaAtivacaoPix) areaAtivacaoPix.style.display = 'none';
        if (areaAtivacaoManual) areaAtivacaoManual.style.display = 'flex';
    });
}

async function carregarCobrancaPix(tentativa = 1) {
    try {
        const chaveAtual = (dadosLicencaAtual && dadosLicencaAtual.chave_licenca) || (inputChaveLicenca && inputChaveLicenca.value ? inputChaveLicenca.value.trim() : '');
        const hwidAtual = (dadosLicencaAtual && dadosLicencaAtual.hwid_maquina) || (inputHwidDisplay && inputHwidDisplay.value && !inputHwidDisplay.value.includes('Carregando') ? inputHwidDisplay.value.trim() : '');
        const qs = new URLSearchParams({ _: String(Date.now()) });
        if (chaveAtual) qs.set('chave', chaveAtual);
        if (hwidAtual) qs.set('hwid', hwidAtual);

        const res = await fetch(`${API_URL}/api/pix/dados-cobranca?${qs.toString()}`);
        const data = await res.json();
        if (data && data.sucesso) {
            dadosCobrancaPix = data;
            if (imgPixQrcode && data.qr_code_base64) {
                imgPixQrcode.src = data.qr_code_base64;
                imgPixQrcode.style.display = 'block';
                if (pixQrLoading) pixQrLoading.style.display = 'none';
            }
            if (inputPixCopiaCola && data.pix_copia_cola) {
                inputPixCopiaCola.value = data.pix_copia_cola;
            }
            if (pixValorDisplay && data.valor_formatado) {
                pixValorDisplay.innerText = data.valor_formatado;
            }
            if (tabBtnPix && data.valor_formatado) {
                tabBtnPix.innerHTML = `💠 PAGAR VIA PIX (${data.valor_formatado})`;
            }
            if (pixBeneficiarioDisplay && data.beneficiario) {
                pixBeneficiarioDisplay.innerText = data.beneficiario;
            }
            if (pixChaveDisplay) {
                pixChaveDisplay.innerText = "Chave Aleatória (QR Code)";
            }
        } else if (tentativa < 3) {
            setTimeout(() => carregarCobrancaPix(tentativa + 1), 1500);
        }
    } catch (e) {
        console.warn("[PIX] Erro ao carregar cobrança:", e);
        if (tentativa < 3) {
            setTimeout(() => carregarCobrancaPix(tentativa + 1), 1500);
        }
    }
}

if (btnCopiarPixCopiaCola) {
    btnCopiarPixCopiaCola.addEventListener('click', async () => {
        if (!inputPixCopiaCola || !inputPixCopiaCola.value) return;
        try {
            await navigator.clipboard.writeText(inputPixCopiaCola.value);
            const original = btnCopiarPixCopiaCola.innerHTML;
            btnCopiarPixCopiaCola.innerHTML = "<span>✓</span> COPIADO!";
            btnCopiarPixCopiaCola.style.background = "#059669";
            setTimeout(() => {
                btnCopiarPixCopiaCola.innerHTML = original;
                btnCopiarPixCopiaCola.style.background = "";
            }, 2000);
        } catch (err) {
            inputPixCopiaCola.select();
            document.execCommand('copy');
            alert("Código PIX copiado com sucesso!");
        }
    });
}

async function verificarPagamentoPixERenovar(silencioso = false) {
    if (!silencioso && btnVerificarPix) {
        btnVerificarPix.disabled = true;
        btnVerificarPix.innerText = "⏳ Verificando no Banco (Asaas/PIX)...";
        if (feedbackPixMsg) feedbackPixMsg.style.display = 'none';
    }

    try {
        if (!dadosCobrancaPix || !dadosCobrancaPix.qr_code_base64) {
            await carregarCobrancaPix();
        }
        if (dadosCobrancaPix && dadosCobrancaPix.fatura_id) {
            try {
                await fetch(`${API_URL}/api/pix/checar-status?fatura_id=${encodeURIComponent(dadosCobrancaPix.fatura_id)}&_=${Date.now()}`);
            } catch (ePix) {
                console.warn("[PIX] Aviso ao checar fatura:", ePix);
            }
        }

        const lic = await checarStatusLicenca(true);
        if (lic && lic.valido) {
            if (feedbackPixMsg) {
                feedbackPixMsg.style.display = 'block';
                feedbackPixMsg.style.background = 'rgba(16, 185, 129, 0.2)';
                feedbackPixMsg.style.color = '#4ade80';
                feedbackPixMsg.innerText = "✓ Pagamento e licença confirmados! Terminal liberado.";
            }
            setTimeout(() => {
                if (modalLicenca && !window._modalLicencaAbertoManual) {
                    modalLicenca.style.display = 'none';
                }
            }, 1500);
            return true;
        } else if (!silencioso) {
            if (feedbackPixMsg) {
                feedbackPixMsg.style.display = 'block';
                feedbackPixMsg.style.background = 'rgba(245, 158, 11, 0.2)';
                feedbackPixMsg.style.color = '#fbbf24';
                feedbackPixMsg.innerText = "⏳ Pagamento ainda aguardando compensação bancária.";
            }
        }
    } catch (err) {
        if (!silencioso && feedbackPixMsg) {
            feedbackPixMsg.style.display = 'block';
            feedbackPixMsg.style.background = 'rgba(239, 68, 68, 0.2)';
            feedbackPixMsg.style.color = '#f87171';
            feedbackPixMsg.innerText = "Erro ao checar status: " + err.message;
        }
    } finally {
        if (!silencioso && btnVerificarPix) {
            btnVerificarPix.disabled = false;
            btnVerificarPix.innerText = "🔄 JÁ PAGUEI / VERIFICAR";
        }
    }
    return false;
}

if (btnVerificarPix) {
    btnVerificarPix.addEventListener('click', () => verificarPagamentoPixERenovar(false));
}

// Monitoramento automático em segundo plano quando o terminal estiver com a tela de bloqueio aberta
setInterval(() => {
    if (modalLicenca && modalLicenca.style.display === 'flex' && (!dadosLicencaAtual || !dadosLicencaAtual.valido)) {
        carregarCobrancaPix(3);
        verificarPagamentoPixERenovar(true);
    }
}, 8000);

// ----------------------------------------------------
// ABA 4: SISTEMA & NUVEM (AUTO-UPDATE)
// ----------------------------------------------------
const btnChecarAtualizacao = document.getElementById('btn-checar-atualizacao');
const btnAplicarAtualizacao = document.getElementById('btn-aplicar-atualizacao');
const statusAtualizacaoMsg = document.getElementById('status-atualizacao-msg');
const badgeVersaoSistema = document.getElementById('badge-versao-sistema');
const btnAbrirModalLicencaSistema = document.getElementById('btn-abrir-modal-licenca-sistema');

if (btnAbrirModalLicencaSistema) {
    btnAbrirModalLicencaSistema.addEventListener('click', () => {
        if (settingsModal) {
            settingsModal.classList.remove('active');
            settingsModal.style.display = 'none';
        }
        if (modalLicenca) {
            modalLicenca.style.display = 'flex';
            carregarCobrancaPix();
            if (dadosLicencaAtual && dadosLicencaAtual.valido && btnFecharModalLicenca) {
                btnFecharModalLicenca.style.display = 'block';
            }
        }
    });
}

if (btnChecarAtualizacao) {
    btnChecarAtualizacao.addEventListener('click', async () => {
        btnChecarAtualizacao.disabled = true;
        btnChecarAtualizacao.innerHTML = "<span>⏳</span> Verificando...";
        if (statusAtualizacaoMsg) {
            statusAtualizacaoMsg.style.display = 'none';
        }
        if (btnAplicarAtualizacao) {
            btnAplicarAtualizacao.style.display = 'none';
        }

        try {
            const res = await fetch(`${API_URL}/checar-atualizacao?_=${Date.now()}`);
            const data = await res.json();

            if (data.sucesso) {
                if (data.versao_atual && badgeVersaoSistema) {
                    badgeVersaoSistema.innerText = `v${data.versao_atual}`;
                }

                if (data.tem_atualizacao) {
                    if (statusAtualizacaoMsg) {
                        statusAtualizacaoMsg.style.display = 'block';
                        statusAtualizacaoMsg.style.background = 'rgba(16, 185, 129, 0.15)';
                        statusAtualizacaoMsg.style.border = '1px solid #10b981';
                        statusAtualizacaoMsg.style.color = '#34d399';
                        statusAtualizacaoMsg.innerHTML = `
                            <strong>Nova versão disponível: v${data.versao_nova}</strong><br>
                            <span>${data.descricao || 'Melhorias de desempenho e correções.'}</span>
                        `;
                    }
                    if (btnAplicarAtualizacao) {
                        btnAplicarAtualizacao.style.display = 'inline-flex';
                    }
                } else {
                    if (statusAtualizacaoMsg) {
                        statusAtualizacaoMsg.style.display = 'block';
                        statusAtualizacaoMsg.style.background = 'rgba(56, 189, 248, 0.12)';
                        statusAtualizacaoMsg.style.border = '1px solid #38bdf8';
                        statusAtualizacaoMsg.style.color = '#38bdf8';
                        statusAtualizacaoMsg.innerHTML = `✓ O sistema já está atualizado na versão mais recente (v${data.versao_atual}).`;
                    }
                }
            } else {
                if (statusAtualizacaoMsg) {
                    statusAtualizacaoMsg.style.display = 'block';
                    statusAtualizacaoMsg.style.background = 'rgba(239, 68, 68, 0.15)';
                    statusAtualizacaoMsg.style.border = '1px solid #ef4444';
                    statusAtualizacaoMsg.style.color = '#f87171';
                    statusAtualizacaoMsg.innerHTML = `✕ ${data.mensagem || 'Não foi possível consultar a nuvem.'}`;
                }
            }
        } catch (err) {
            if (statusAtualizacaoMsg) {
                statusAtualizacaoMsg.style.display = 'block';
                statusAtualizacaoMsg.style.background = 'rgba(239, 68, 68, 0.15)';
                statusAtualizacaoMsg.style.border = '1px solid #ef4444';
                statusAtualizacaoMsg.style.color = '#f87171';
                statusAtualizacaoMsg.innerHTML = `✕ Erro de conexão: ${err.message}`;
            }
        } finally {
            btnChecarAtualizacao.disabled = false;
            btnChecarAtualizacao.innerHTML = "<span>🔄</span> Verificar Atualizações";
        }
    });
}

if (btnAplicarAtualizacao) {
    btnAplicarAtualizacao.addEventListener('click', async () => {
        if (!confirm("Deseja aplicar a atualização agora? Os arquivos do sistema serão atualizados pela nuvem e o servidor será reiniciado automaticamente.")) return;

        btnAplicarAtualizacao.disabled = true;
        btnAplicarAtualizacao.innerHTML = "<span>⏳</span> Baixando e atualizando...";

        try {
            const res = await fetch(`${API_URL}/aplicar-atualizacao`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();

            if (data.sucesso) {
                if (statusAtualizacaoMsg) {
                    statusAtualizacaoMsg.style.display = 'block';
                    statusAtualizacaoMsg.style.background = 'rgba(16, 185, 129, 0.2)';
                    statusAtualizacaoMsg.style.border = '1px solid #10b981';
                    statusAtualizacaoMsg.style.color = '#4ade80';
                    statusAtualizacaoMsg.innerHTML = `✓ ${data.mensagem}<br><strong>Reiniciando o sistema em instantes...</strong>`;
                }

                // Exibe o overlay de reinicialização após 1.2s e recarrega a página
                setTimeout(() => {
                    const overlay = document.getElementById('overlay-reiniciando');
                    const overlayMsg = document.getElementById('overlay-reiniciando-msg');
                    if (overlay) {
                        if (overlayMsg) overlayMsg.innerText = "Atualização instalada com sucesso! Reiniciando o servidor...";
                        overlay.style.display = 'flex';
                    }
                    setTimeout(() => {
                        window.location.reload();
                    }, 4500);
                }, 1200);
            } else {
                btnAplicarAtualizacao.disabled = false;
                btnAplicarAtualizacao.innerHTML = "<span>⬇️</span> Baixar e Atualizar Agora";
                if (statusAtualizacaoMsg) {
                    statusAtualizacaoMsg.style.display = 'block';
                    statusAtualizacaoMsg.style.background = 'rgba(239, 68, 68, 0.2)';
                    statusAtualizacaoMsg.style.border = '1px solid #ef4444';
                    statusAtualizacaoMsg.style.color = '#f87171';
                    statusAtualizacaoMsg.innerHTML = `✕ Falha na atualização: ${data.mensagem}`;
                }
            }
        } catch (err) {
            btnAplicarAtualizacao.disabled = false;
            btnAplicarAtualizacao.innerHTML = "<span>⬇️</span> Baixar e Atualizar Agora";
            if (statusAtualizacaoMsg) {
                statusAtualizacaoMsg.style.display = 'block';
                statusAtualizacaoMsg.style.background = 'rgba(239, 68, 68, 0.2)';
                statusAtualizacaoMsg.style.border = '1px solid #ef4444';
                statusAtualizacaoMsg.style.color = '#f87171';
                statusAtualizacaoMsg.innerHTML = `✕ Erro: ${err.message}`;
            }
        }
    });
}

// Inicialização: verifica licença e carrega as configurações
checarStatusLicenca();
setInterval(checarStatusLicenca, 10 * 60 * 1000); // Checa a cada 10 min
carregarConfiguracoes();

// Checagem e aplicação automática de novas versões na nuvem ao abrir o app
async function checarAtualizacaoAutomatica() {
    try {
        const res = await fetch(`${API_URL}/checar-atualizacao?_=${Date.now()}`);
        const data = await res.json();
        if (data && data.sucesso) {
            if (data.versao_atual && badgeVersaoSistema) {
                badgeVersaoSistema.innerText = `v${data.versao_atual}`;
            }
            if (data.tem_atualizacao) {
                const overlay = document.getElementById('overlay-reiniciando');
                const overlayMsg = document.getElementById('overlay-reiniciando-msg');
                if (overlay) {
                    if (overlayMsg) {
                        overlayMsg.innerText = `Nova versão v${data.versao_nova} encontrada! Atualizando automaticamente...`;
                    }
                    overlay.style.display = 'flex';
                }
                const resUpd = await fetch(`${API_URL}/aplicar-atualizacao`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const dataUpd = await resUpd.json();
                if (dataUpd && dataUpd.sucesso) {
                    if (overlay && overlayMsg) {
                        overlayMsg.innerText = `Atualizado para v${data.versao_nova} com sucesso! Reiniciando...`;
                    }
                    setTimeout(() => {
                        window.location.reload();
                    }, 4500);
                } else if (overlay) {
                    overlay.style.display = 'none';
                }
            }
        }
    } catch (e) {
        // Falha silenciosa em caso de oscilação de rede
    }
}
setTimeout(checarAtualizacaoAutomatica, 4500);

// ========================================================
// GUIA DE OPERAÇÃO POR EMPRESA (MODAL DE AJUDA)
// ========================================================
const modalAjuda = document.getElementById('modal-ajuda');
const btnAbrirAjuda = document.getElementById('btn-abrir-ajuda');
const btnFecharAjuda = document.getElementById('btn-fechar-ajuda');
const btnEntendiAjuda = document.getElementById('btn-entendi-ajuda');

window.trocarAbaAjuda = function(tabId) {
    const temasAba = {
        'ajuda-anjun': { border: '#10b981', bg: 'rgba(16, 185, 129, 0.2)', color: '#34d399' },
        'ajuda-imile': { border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.22)', color: '#c4b5fd' },
        'ajuda-loggi': { border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.22)', color: '#fbbf24' },
        'ajuda-paineis': { border: '#38bdf8', bg: 'rgba(56, 189, 248, 0.2)', color: '#38bdf8' },
        'ajuda-vantagens': { border: '#ec4899', bg: 'rgba(236, 72, 153, 0.2)', color: '#f472b6' }
    };

    const botoes = document.querySelectorAll('.ajuda-tab-btn');
    botoes.forEach(btn => {
        const alvo = btn.getAttribute('data-ajuda-tab');
        if (alvo === tabId) {
            const t = temasAba[tabId] || temasAba['ajuda-paineis'];
            btn.classList.add('active');
            btn.style.borderColor = t.border;
            btn.style.background = t.bg;
            btn.style.color = t.color;
        } else {
            btn.classList.remove('active');
            btn.style.borderColor = '#334155';
            btn.style.background = '#0d121f';
            btn.style.color = '#cbd5e1';
        }
    });

    const paineis = document.querySelectorAll('.ajuda-tab-panel');
    paineis.forEach(p => {
        p.style.display = (p.id === tabId) ? 'flex' : 'none';
    });
};

function fecharModalAjuda() {
    if (modalAjuda) modalAjuda.style.display = 'none';
    if (input) input.focus();
}

if (btnAbrirAjuda) {
    btnAbrirAjuda.addEventListener('click', () => {
        if (!modalAjuda) return;
        const platAtual = ((platformSelector ? platformSelector.value : '') || plataformaAtiva || 'anjun').toLowerCase();
        if (platAtual.includes('imile')) {
            window.trocarAbaAjuda('ajuda-imile');
        } else if (platAtual.includes('loggi')) {
            window.trocarAbaAjuda('ajuda-loggi');
        } else {
            window.trocarAbaAjuda('ajuda-anjun');
        }
        modalAjuda.style.display = 'flex';
    });
}

if (btnFecharAjuda) {
    btnFecharAjuda.addEventListener('click', fecharModalAjuda);
}

if (btnEntendiAjuda) {
    btnEntendiAjuda.addEventListener('click', fecharModalAjuda);
}

if (modalAjuda) {
    modalAjuda.addEventListener('click', (e) => {
        if (e.target === modalAjuda) fecharModalAjuda();
    });
}

