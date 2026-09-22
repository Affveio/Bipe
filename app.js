// Elementos Principais do Dashboard
const input = document.getElementById('qr-input');
const statusPanel = document.getElementById('status-panel');
const statusLabel = document.getElementById('status-label');
const subStatusLabel = document.getElementById('sub-status-label');
const totalContador = document.getElementById('total-contador');
const historyLog = document.getElementById('history-log');

// Elementos de Controle do Cabeçalho
const platformSelector = document.getElementById('platform-selector');
const containerPacoteSolto = document.getElementById('container-pacote-solto');
const btnPacoteSolto = document.getElementById('btn-pacote-solto');
const statusPacoteSolto = document.getElementById('status-pacote-solto');
const voiceSelector = document.getElementById('voice-selector');
const consultToggle = document.getElementById('consult-toggle');
let pacoteSoltoAtivo = (localStorage.getItem('imile_pacote_solto') === 'true');

// Elementos de Atribuição
const driverSelect = document.getElementById('driver-select');
const btnIniciarLote = document.getElementById('btn-iniciar-lote');
const btnFinalizarLote = document.getElementById('btn-finalizar-lote');
const atribuicaoStatusArea = document.getElementById('atribuicao-status-area');
const atribuicaoDriverName = document.getElementById('atribuicao-driver-name');
const atribuicaoCounter = document.getElementById('atribuicao-counter');
const atribuicaoFeedback = document.getElementById('atribuicao-feedback');
const driverCitiesListBox = document.getElementById('driver-cities-list-box');

// Elementos de Atribuição Multi-Cidades (Exclusivo Loggi)
const containerDriverStandard = document.getElementById('container-driver-standard');
const containerLoggiCities = document.getElementById('container-loggi-cities');
const loggiCityAddSelect = document.getElementById('loggi-city-add-select');
const loggiSelectedCitiesTags = document.getElementById('loggi-selected-cities-tags');
const btnLimparCidadesLoggi = document.getElementById('btn-limpar-cidades-loggi');
const driverCitiesLabel = document.getElementById('driver-cities-label');
let cidadesLoggiSelecionadas = [];

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

// FORÇA FOCO ABSOLUTO: Garante que o leitor de QR Code sempre escreva no input oculto, exceto quando clica em seletores
document.addEventListener('click', (e) => {
    if (e.target.closest('select') || e.target.closest('option') || e.target.closest('input') || e.target.closest('table') || e.target.closest('.table-container') || e.target.closest('#modal-confirmar-motorista') || e.target.closest('#settings-modal') || modalConfirmacaoAberto || (settingsModal && settingsModal.classList.contains('active'))) {
        return;
    }
    if (input) input.focus();
});

window.addEventListener('load', () => {
    if (input) input.focus();
});

// 1. CARREGAR CONFIGURAÇÕES INICIAIS DO BACKEND
async function carregarConfiguracoes() {
    try {
        const res = await fetch(`${API_URL}/configuracoes?_=${Date.now()}`);
        if (!res.ok) throw new Error("Erro ao carregar");
        
        const data = await res.json();
        todasPlataformas = data.plataformas || {};
        todosMotoristas = normalizarMotoristas(data.motoristas);
        todasCidades = (data.cidades || []).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
        plataformaAtiva = data.plataforma_ativa || "";
        if (consultToggle) {
            consultToggle.value = data.modo_consulta ? "ativado" : "desativado";
            consultToggle.style.color = data.modo_consulta ? "#4ade80" : "#f87171";
        }

        // Renderiza o seletor de plataforma ativa
        atualizarSeletorPlataformas();

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

                // Popula a tabela de histórico inicial do operador (apenas os de HOJE)
                historyLog.innerHTML = "";
                const bipsHoje = histData.filter(item => {
                    const dataBip = item.timestamp ? item.timestamp.substring(0, 10) : "";
                    return dataBip === hojeStr;
                });
                const bipsExibidos = bipsHoje.slice(-150).reverse();
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

        // Se o backend já possuir uma plataforma ativa iniciada, recupera a fila
        if (plataformaAtiva) {
            recuperarFilaSalva();
        }
        
        atualizarSeletorMotoristas();
        sincronizarStatusLoteAtivo();
        atualizarDivergenciasPendentes();
        carregarLotesFinalizados();

    } catch (e) {
        console.error("Falha ao comunicar com o servidor. Aguardando a inicialização...", e);
        if (platformSelector) {
            platformSelector.innerHTML = '<option value="">Iniciando servidor local...</option>';
        }
        setTimeout(carregarConfiguracoes, 2000);
    }
}

// Ajusta exibição do botão finalizar e do modo pacote solto baseado na plataforma ativa
function atualizarBotoesPainel() {
    if (btnFinalizarLote) {
        btnFinalizarLote.style.display = 'block';
    }
    atualizarVisibilidadePacoteSolto();
}

// 2. ATUALIZAR SELETOR DE PLATAFORMAS (DROP-DOWN)
function atualizarSeletorPlataformas() {
    const keys = Object.keys(todasPlataformas);
    if (keys.length === 0) {
        platformSelector.innerHTML = '<option value="">Nenhuma plataforma cadastrada</option>';
        return;
    }

    let optionsHtml = '';
    if (!plataformaAtiva) {
        optionsHtml += '<option value="" disabled selected style="color: #64748b;">Escolha a plataforma...</option>';
    }
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

// Listener para alteração da Plataforma Ativa pelo usuário
platformSelector.addEventListener('change', (e) => {
    const platSelecionada = e.target.value;
    atualizarVisibilidadePacoteSolto();
    atualizarSeletorMotoristas();
    if (platSelecionada) {
        selecionarPlataformaNoBackend(platSelecionada);
    }
});

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


// ========================================================
// CAPTURA DO BIP E INTEGRAÇÃO DE SÍNTESE DE VOZ/SOM
// ========================================================

function emitirBeepErro() {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    
    oscillator.type = 'sawtooth';
    oscillator.frequency.setValueAtTime(120, audioCtx.currentTime); // Som áspero
    gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
    
    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    oscillator.start();
    oscillator.stop(audioCtx.currentTime + 0.4);
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

function falarCidade(nomeCidade) {
    if (typeof window.speechSynthesis === 'undefined') return;
    
    // Cancela qualquer fala anterior
    window.speechSynthesis.cancel();
    
    // Aumentado para 250ms para dar tempo ao sintetizador do Windows/Chrome/Edge
    // processar a limpeza da fila. Isso resolve o bug onde vozes "Online (Natural)"
    // travam ou falham ao tentar falar logo após um cancel().
    setTimeout(() => {
        const fala = new SpeechSynthesisUtterance(nomeCidade);
        fala.lang = 'pt-BR';
        fala.rate = 1.3; // Velocidade ideal
        
        const vozEscolhidaNome = localStorage.getItem('voz_selecionada') || voiceSelector.value;
        let vozUsada = null;
        
        if (vozEscolhidaNome) {
            vozUsada = voices.find(v => v.name === vozEscolhidaNome);
            if (vozUsada) {
                fala.voice = vozUsada;
                fala.lang = vozUsada.lang;
            }
        }
        
        // Se a voz selecionada falhar (ex: oscilação na voz online da nuvem),
        // fala a própria cidade diretamente usando uma voz offline confiável,
        // sem emitir avisos incômodos nem interromper a triagem.
        fala.onerror = (e) => {
            if (e.error === 'interrupted' || e.error === 'canceled') return;
            console.warn(`[Voz] Falha na voz principal (${e.error}). Usando voz local offline...`);
            
            const fallback = new SpeechSynthesisUtterance(nomeCidade);
            fallback.lang = 'pt-BR';
            fallback.rate = 1.3;
            
            // Procura Francisca, Antônio, Maria, Daniel ou Google offline
            const vozOffline = voices.find(v => 
                (v.name.includes("Francisca") || v.name.includes("Antônio") || v.name.includes("Maria") || v.name.includes("Daniel") || v.name.includes("Google")) && 
                !v.name.includes("Online")
            );
            if (vozOffline) {
                fallback.voice = vozOffline;
            }
            window.speechSynthesis.speak(fallback);
        };
        
        window.speechSynthesis.speak(fala);
    }, 250);
}

function adicionarAoHistorico(codigo, recebedor, cidade, status, classeBadge) {
    const agora = new Date().toLocaleTimeString('pt-BR');
    const novaLinha = document.createElement('tr');
    
    novaLinha.innerHTML = `
        <td style="color: #64748b;">${agora}</td>
        <td style="font-family: monospace; cursor: pointer; transition: all 0.2s;" class="copyable-code" title="Clique para copiar (${codigo})">${codigo}</td>
        <td title="${cidade}">${cidade}</td>
        <td style="text-align: center;"><span class="status-badge ${classeBadge}">${status}</span></td>
    `;
    
    historyLog.insertBefore(novaLinha, historyLog.firstChild);
    
    if (historyLog.children.length > 150) {
        historyLog.removeChild(historyLog.lastChild);
    }
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

    statusPanel.className = 'status-container awaiting';
    statusLabel.innerText = "PROCESSANDO...";
    subStatusLabel.innerText = `Analisando pacote ${codigo}${textoFila}`;

    if (motorista) {
        atribuicaoFeedback.innerText = `Atribuindo pacote ${codigo}...`;
        atribuicaoFeedback.style.color = "#38bdf8";
    }

    try {
        const resposta = await fetch(`${API_URL}/bip`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                codigo: codigo, 
                plataforma: plataforma, 
                motorista: motorista,
                cidades_selecionadas: (cidades_selecionadas && cidades_selecionadas.length > 0) ? cidades_selecionadas : (motorista ? [motorista] : []),
                pacote_solto: Boolean(pacote_solto),
                confirmado_reabertura: confirmadoReaberturaAtivo
            })
        });

        const resultado = await resposta.json();

        if (resposta.ok && resultado.status === 'sucesso') {
            confirmadoReaberturaAtivo = false;
            const isDup = resultado.duplicado === true;
            
            if (isDup) {
                statusPanel.className = 'status-container awaiting'; // Cor amarela/laranja de atenção
                statusLabel.innerText = "DUPLICADO / REATRIBUÍDO";
                if (resultado.mesmo_motorista) {
                    subStatusLabel.innerText = `Reatribuído para ${resultado.motorista} (Já bipado às ${resultado.timestamp_anterior || '---'})`;
                } else {
                    subStatusLabel.innerText = `Reatribuído de ${resultado.motorista_anterior || '---'} para ${resultado.motorista}`;
                }
                falarCidade(`Pacote duplicado, reatribuído para o motorista ${resultado.motorista}`);
            } else {
                statusPanel.className = 'status-container success';
                statusLabel.innerText = resultado.cidade;
                subStatusLabel.innerText = `Recebedor: ${resultado.recebedor}${textoFila}`;
            }
            
            // Se for duplicado e já tiver sido bipado hoje, não incrementa para não duplicar contagem do dia
            const hojeStr = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;
            const hojeBR = `${String(new Date().getDate()).padStart(2, '0')}/${String(new Date().getMonth() + 1).padStart(2, '0')}/${new Date().getFullYear()}`;
            const jaBipadoHoje = Boolean(isDup && resultado.timestamp_anterior && (resultado.timestamp_anterior.includes(hojeStr) || resultado.timestamp_anterior.includes(hojeBR)));

            if (!jaBipadoHoje) {
                contagemSucesso++;
                totalContador.innerText = contagemSucesso;
            }
            
            adicionarAoHistorico(codigo, isDup ? "DUPLICADO" : resultado.recebedor, resultado.cidade, "OK", isDup ? "badge-proc" : "badge-ok");

            if (motorista) {
                let textCount = `${resultado.contagem} PACOTES BIPADOS`;
                if (resultado.contagem_site !== null && resultado.contagem_site !== undefined) {
                    textCount += ` (Site: ${resultado.contagem_site})`;
                }
                atribuicaoCounter.innerText = textCount;
                if (isDup) {
                    atribuicaoFeedback.innerText = `[Aviso] Pacote Duplicado! Reatribuído para o motorista ${motorista}.`;
                    atribuicaoFeedback.style.color = "#fbbf24"; // Amarelo
                } else {
                    atribuicaoFeedback.innerText = `Sucesso! Pacote ${codigo} atribuído.`;
                    atribuicaoFeedback.style.color = "#4ade80"; // Verde
                }
            }
        } else if (resultado.status === 'finalizado_limite') {
            statusPanel.className = 'status-container success';
            statusLabel.innerText = resultado.cidade;
            subStatusLabel.innerText = `Recebedor: ${resultado.recebedor}${textoFila}`;
            
            const isDupLim = resultado.duplicado === true;
            const hojeStr = `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}`;
            const hojeBR = `${String(new Date().getDate()).padStart(2, '0')}/${String(new Date().getMonth() + 1).padStart(2, '0')}/${new Date().getFullYear()}`;
            const jaBipadoHojeLim = Boolean(isDupLim && resultado.timestamp_anterior && (resultado.timestamp_anterior.includes(hojeStr) || resultado.timestamp_anterior.includes(hojeBR)));

            if (!jaBipadoHojeLim) {
                contagemSucesso++;
                totalContador.innerText = contagemSucesso;
            }
            
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "OK", "badge-ok");

            if (motorista) {
                atribuicaoCounter.innerText = `0 PACOTES BIPADOS`;
                atribuicaoFeedback.innerText = `Lote de 200 concluído! Iniciado novo lote para ${resultado.motorista}...`;
                atribuicaoFeedback.style.color = "#38bdf8";
                carregarLotesFinalizados();
            }
        } else if (resultado.status === 'divergente') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "DIVERGENTE";
            
            const cidadePacote = (resultado.cidade && resultado.cidade !== '---' && resultado.cidade !== 'Não Consultada') ? resultado.cidade : '';
            if (cidadePacote) {
                subStatusLabel.innerText = `Pacote de: ${cidadePacote} | Esperado: ${resultado.motorista_esperado}${textoFila}`;
                falarCidade(`Divergente! Pacote de ${cidadePacote}`);
            } else {
                subStatusLabel.innerText = `Destinado a: ${resultado.motorista_esperado}${textoFila}`;
                falarCidade(`Divergente! Pertence ao motorista ${resultado.motorista_esperado}`);
            }
            
            emitirBeepErro();
            
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "DIVERGENTE", "badge-err");
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Falha: ${resultado.mensagem}`;
                atribuicaoFeedback.style.color = "#f87171";
            }
            
            // Trava a tela do operador
            travarSistemaDivergencia(codigo, resultado.cidade, resultado.motorista_esperado, motorista);

        } else if (resultado.status === 'fora_de_rota') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "FORA DA BASE";
            subStatusLabel.innerText = `${resultado.mensagem}${textoFila}`;
            
            falarCidade("Pacote não pertence a esta Base");
            emitirBeepErro();
            adicionarAoHistorico(codigo, resultado.recebedor, resultado.cidade, "FORA DA BASE", "badge-err");
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Falha: ${resultado.mensagem}`;
                atribuicaoFeedback.style.color = "#f87171";
            }
        } else if (resultado.status === 'erro_sem_entrada') {
            statusPanel.className = 'status-container error';
            statusLabel.innerText = "SEM ENTRADA";
            subStatusLabel.innerText = `${resultado.mensagem}${textoFila}`;
            
            falarCidade("Pacote sem entrada");
            emitirBeepErro();
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
            subStatusLabel.innerText = `Já bipado para ${resultado.motorista}${textoFila}`;
            
            falarCidade("Pacote duplicado");
            emitirBeepErro();
            adicionarAoHistorico(codigo, "---", resultado.cidade, "DUPLICADO", "badge-err");
            
            if (motorista) {
                atribuicaoFeedback.innerText = `Falha: Pacote já bipado para ${resultado.motorista}`;
                atribuicaoFeedback.style.color = "#f87171";
            }
            
            // Trava a tela com o aviso de duplicado
            travarSistemaDuplicado(codigo, resultado.timestamp, resultado.motorista, resultado.cidade);
        } else if (resultado.status === 'chrome_fechado') {
            processandoFila = false;
            await prepararSessaoEMostrarConfirmacao(motorista, plataforma, filaBipes.length, false);
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

        statusPanel.className = 'status-container error';
        statusLabel.innerText = "ERRO";
        subStatusLabel.innerText = `${erro.message}${textoFila}`;
        
        emitirBeepErro();
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

        // Inicia o processamento caso a fila esteja ociosa
        if (!processandoFila) {
            processarProximoDaFila();
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
    
    let placeholder = "+ Adicionar Cidade ao Grupo...";
    if (cidadesLoggiSelecionadas.length === 0) {
        placeholder = "⭐ Selecione a Cidade Principal (Grupo Aba 3)...";
    }
    
    loggiCityAddSelect.innerHTML = `<option value="">${placeholder}</option>` +
        cidadesDisponiveis.map(c => `<option value="${c}">${c}</option>`).join('');
}

function renderizarBadgesCidadesLoggi() {
    if (!loggiSelectedCitiesTags) return;
    
    if (cidadesLoggiSelecionadas.length === 0) {
        loggiSelectedCitiesTags.innerHTML = `<span style="color: #64748b; font-style: italic; font-size: 0.7rem;">Nenhuma cidade selecionada</span>`;
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
                <div class="loggi-city-pill primary" title="Cidade Principal (Usada para nome e busca do grupo na Aba 3)">
                    <span>⭐ 1ª ${cidade} (Principal)</span>
                    <span class="pill-remove" onclick="removerCidadeLoggi(0)" title="Remover cidade">✕</span>
                </div>
            `;
        } else {
            return `
                <div class="loggi-city-pill" title="${idx + 1}ª Cidade autorizada no grupo">
                    <span>${idx + 1}ª ${cidade}</span>
                    <span class="pill-remove" onclick="removerCidadeLoggi(${idx})" title="Remover cidade">✕</span>
                </div>
            `;
        }
    }).join('');
}

window.removerCidadeLoggi = function(index) {
    if (index >= 0 && index < cidadesLoggiSelecionadas.length) {
        cidadesLoggiSelecionadas.splice(index, 1);
        salvarCidadesLoggiLocalStorage();
        popularDropdownCidadesLoggi();
        renderizarBadgesCidadesLoggi();
        atualizarCidadesDoMotoristaSelecionado();
        atualizarContagemAoMudarMotorista();
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

// Configura listeners do seletor de cidades da Loggi
if (loggiCityAddSelect) {
    loggiCityAddSelect.addEventListener('change', () => {
        const val = loggiCityAddSelect.value.trim();
        if (val && !cidadesLoggiSelecionadas.includes(val)) {
            cidadesLoggiSelecionadas.push(val);
            salvarCidadesLoggiLocalStorage();
            popularDropdownCidadesLoggi();
            renderizarBadgesCidadesLoggi();
            atualizarCidadesDoMotoristaSelecionado();
            atualizarContagemAoMudarMotorista();
        }
    });
}

if (btnLimparCidadesLoggi) {
    btnLimparCidadesLoggi.addEventListener('click', () => {
        if (cidadesLoggiSelecionadas.length > 0) {
            cidadesLoggiSelecionadas = [];
            salvarCidadesLoggiLocalStorage();
            popularDropdownCidadesLoggi();
            renderizarBadgesCidadesLoggi();
            atualizarCidadesDoMotoristaSelecionado();
            atualizarContagemAoMudarMotorista();
        }
    });
}

// Preenche o dropdown de motoristas na tela de atribuição
function atualizarSeletorMotoristas() {
    const platSelecionada = (platformSelector ? platformSelector.value : "") || plataformaAtiva;
    
    if (platSelecionada === 'loggi') {
        if (containerDriverStandard) containerDriverStandard.style.display = 'none';
        if (containerLoggiCities) containerLoggiCities.style.display = 'flex';
        if (driverCitiesLabel) driverCitiesLabel.innerText = "CIDADES DO GRUPO (VALIDAÇÃO ABA 3):";
        
        carregarCidadesLoggiLocalStorage();
        popularDropdownCidadesLoggi();
        renderizarBadgesCidadesLoggi();
    } else {
        if (containerDriverStandard) containerDriverStandard.style.display = 'flex';
        if (containerLoggiCities) containerLoggiCities.style.display = 'none';
        if (driverCitiesLabel) driverCitiesLabel.innerText = "CIDADES VINCULADAS:";
        
        if (driverSelect) {
            const motoristasList = Array.isArray(todosMotoristas) 
                ? todosMotoristas.map(m => m.motorista) 
                : Object.values(todosMotoristas);
            const motoristasSet = new Set(motoristasList.map(m => (m || '').trim()).filter(m => m && m !== "Sem Motorista"));
            const motoristasOrdenados = Array.from(motoristasSet).sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            driverSelect.innerHTML = '<option value="">Apenas Entrada (Sem Atribuição)</option>' + 
                motoristasOrdenados.map(m => `<option value="${m}">${m}</option>`).join('');
        }
    }
        
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
        const motorista = driverSelect.value;
        if (!motorista) {
            alert("Selecione um motorista primeiro.");
            if (input) input.focus();
            return;
        }
        if (!confirm(`Confirmar encerramento e emissão da folha de entrega para o motorista "${motorista}"?`)) {
            if (input) input.focus();
            return;
        }

        btnFinalizarLote.disabled = true;
        btnFinalizarLote.innerText = "FINALIZANDO...";

        try {
            const res = await fetch(`${API_URL}/atribuicao/finalizar`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ motorista: motorista })
            });
            const data = await res.json();

            if (res.ok) {
                atribuicaoCounter.innerText = "0 pacotes bipados";
                atribuicaoFeedback.innerText = "Pronto para iniciar";
                carregarLotesFinalizados();
                alert(`Folha de entrega do motorista "${motorista}" emitida com sucesso!`);
            } else {
                alert("Erro ao finalizar lote: " + data.mensagem);
            }
        } catch (e) {
            alert("Erro de conexão: " + e.message);
        } finally {
            btnFinalizarLote.disabled = false;
            btnFinalizarLote.innerText = "FINALIZAR LOTE ATIVO";
            if (input) input.focus();
        }
    });
}

// --- SISTEMA DE LOTES FINALIZADOS ---
const lotesFinalizadosLog = document.getElementById('lotes-finalizados-log');
let lotesFinalizadosCarregados = [];
let colunaOrdenacaoAtual = 'quantidade';
let ordenacaoAscendente = false; // Começa decrescente (do maior para o menor) por padrão

async function carregarLotesFinalizados() {
    if (!lotesFinalizadosLog) return;
    try {
        const res = await fetch(`${API_URL}/atribuicao/lotes-finalizados?_=${Date.now()}`);
        if (res.ok) {
            lotesFinalizadosCarregados = await res.json();
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
    
    const listaOrdenada = [...lotesFinalizadosCarregados].sort((a, b) => {
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

function renderizarLotesFinalizados(lista) {
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
    lotesFinalizadosLog.innerHTML = lista.map(item => {
        return `
            <tr class="bipados-motorista-row">
                <td class="bipados-col-motorista">${item.motorista}</td>
                <td class="bipados-col-cidades" title="${item.cidades}">${item.cidades}</td>
                <td class="bipados-col-plat">${item.plataforma || 'Anjun'}</td>
                <td class="bipados-col-qtd">${item.quantidade}</td>
            </tr>
        `;
    }).join('');
}

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
    const bottomGrids = document.querySelector('.bottom-grids');

    if (!lista || lista.length === 0) {
        if (sectionDiv) sectionDiv.style.display = 'none';
        if (bottomGrids) bottomGrids.classList.remove('has-divergencias');
        if (divergenciasLog) divergenciasLog.innerHTML = '';
        return;
    }

    if (sectionDiv) sectionDiv.style.display = 'flex';
    if (bottomGrids) bottomGrids.classList.add('has-divergencias');

    divergenciasLog.innerHTML = lista.map(item => {
        return `
            <tr>
                <td style="font-family: monospace; color: #f87171; font-weight: bold; font-size: 0.82rem; cursor: pointer; transition: all 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 130px;" class="copyable-code" title="Clique para copiar (${item.codigo})">${item.codigo}</td>
                <td style="color: #cbd5e1; font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 90px;" title="${item.motorista_lote}">${item.motorista_lote}</td>
                <td style="color: #4ade80; font-weight: bold; font-size: 0.8rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 110px;" title="${item.motorista_esperado}">${item.motorista_esperado}</td>
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
    
    if (platSelecionada === 'loggi') {
        if (cidadesLoggiSelecionadas.length === 0) {
            driverCitiesListBox.innerHTML = `<span style="color: #64748b; font-style: italic; font-weight: normal; font-size: 0.75rem;">Nenhuma cidade selecionada</span>`;
            return;
        }
        
        driverCitiesListBox.innerHTML = cidadesLoggiSelecionadas.map((c, idx) => {
            if (idx === 0) {
                return `
                    <div style="display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid #1a1d24;">
                        <span style="color: #fbbf24; font-size: 0.78rem;">⭐</span>
                        <span style="color: #fbbf24; font-size: 0.82rem; font-weight: 800; letter-spacing: 0.3px;">1. ${c} (Grupo Aba 3)</span>
                    </div>
                `;
            } else {
                return `
                    <div style="display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid #1a1d24;">
                        <span style="color: #0284c7; font-size: 0.7rem;">➔</span>
                        <span style="color: #38bdf8; font-size: 0.82rem; font-weight: 600; letter-spacing: 0.3px;">${idx + 1}. ${c} (Autorizada no lote)</span>
                    </div>
                `;
            }
        }).join('');
        return;
    }
    
    const motorista = driverSelect ? driverSelect.value : "";
    if (!motorista) {
        driverCitiesListBox.innerHTML = `<span style="color: #64748b; font-style: italic; font-weight: normal; font-size: 0.75rem;">Nenhum motorista selecionado</span>`;
        return;
    }
        const cidades = [];
        if (Array.isArray(todosMotoristas)) {
            for (const item of todosMotoristas) {
                if (item.motorista && item.motorista.trim().toLowerCase() === motorista.trim().toLowerCase()) {
                    if (!cidades.includes(item.cidade)) {
                        cidades.push(item.cidade);
                    }
                }
            }
        } else {
            for (const [cidade, mot] of Object.entries(todosMotoristas)) {
                if (mot.trim().toLowerCase() === motorista.trim().toLowerCase()) {
                    if (!cidades.includes(cidade)) {
                        cidades.push(cidade);
                    }
                }
            }
        }
        
        if (cidades.length > 0) {
            cidades.sort((a, b) => a.localeCompare(b, 'pt-BR', { sensitivity: 'base' }));
            driverCitiesListBox.innerHTML = cidades.map(c => `
                <div style="display: flex; align-items: center; gap: 6px; padding: 4px 0; border-bottom: 1px solid #1a1d24;">
                    <span style="color: #0284c7; font-size: 0.7rem;">➔</span>
                    <span style="color: #38bdf8; font-size: 0.82rem; letter-spacing: 0.3px;">${c}</span>
                </div>
            `).join('');
        } else {
            driverCitiesListBox.innerHTML = `<span style="color: #ef4444; font-size: 0.75rem;">Nenhuma cidade vinculada</span>`;
        }
}

async function atualizarContagemAoMudarMotorista() {
    atualizarCidadesDoMotoristaSelecionado();
    
    const motorista = driverSelect.value;
    if (!motorista) {
        atribuicaoCounter.innerText = "0 pacotes bipados";
        atribuicaoFeedback.innerText = "Pronto para iniciar";
        return;
    }
    
    try {
        const res = await fetch(`${API_URL}/atribuicao/status?_=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            if (data.motorista && data.motorista.toLowerCase() === motorista.toLowerCase()) {
                atribuicaoCounter.innerText = `${data.contagem} PACOTES BIPADOS`;
                atribuicaoFeedback.innerText = `Lote ativo em execução para ${motorista}...`;
            } else {
                atribuicaoCounter.innerText = "0 pacotes bipados";
                atribuicaoFeedback.innerText = `Pronto para iniciar lote de ${motorista}...`;
            }
        }
    } catch (e) {
        atribuicaoCounter.innerText = "0 pacotes bipados";
    }
}

if (driverSelect) {
    driverSelect.addEventListener('change', atualizarContagemAoMudarMotorista);
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
const formMotorista = document.getElementById('form-motorista');
const motCidadeSelect = document.getElementById('mot-cidade-select');
const motNome = document.getElementById('mot-nome');

// Elementos da Aba Credenciais
const modalPlatSelector = document.getElementById('modal-plat-selector');
const modalLoginUser = document.getElementById('modal-login-user');
const modalLoginPass = document.getElementById('modal-login-pass');
const btnModalSalvar = document.getElementById('btn-modal-salvar');

let motoristasPlataformaModal = [];

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

function fecharModalConfiguracoes() {
    if (settingsModal) {
        settingsModal.classList.remove('active');
        settingsModal.style.display = 'none';
    }
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

window.editarCidadeModal = async (cidadeAntiga) => {
    const novaCidade = prompt(`Editar nome da cidade "${cidadeAntiga}":`, cidadeAntiga);
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
    if (!confirm(`Deseja realmente remover a cidade "${cidade}"? Isso também removerá todos os mapeamentos de motoristas associados a ela.`)) return;

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

async function atualizarMotoristasPlataformaModal() {
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : "";
    if (!platId) return;

    try {
        const res = await fetch(`${API_URL}/configuracoes?plataforma=${platId}&_=${Date.now()}`);
        if (res.ok) {
            const data = await res.json();
            motoristasPlataformaModal = normalizarMotoristas(data.motoristas);
            renderizarListaMotoristasModal();
        }
    } catch (err) {
        console.error("Erro ao carregar motoristas no modal:", err);
    }
}

if (motoristaPlataformaSelect) {
    motoristaPlataformaSelect.addEventListener('change', () => {
        atualizarMotoristasPlataformaModal();
    });
}

function renderizarListaMotoristasModal() {
    if (!motoristasListBody) return;

    motoristasPlataformaModal.sort((a, b) => {
        const compCid = a.cidade.localeCompare(b.cidade, 'pt-BR', { sensitivity: 'base' });
        if (compCid !== 0) return compCid;
        return a.motorista.localeCompare(b.motorista, 'pt-BR', { sensitivity: 'base' });
    });

    if (motoristasPlataformaModal.length === 0) {
        motoristasListBody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: #64748b;">Nenhum motorista cadastrado para esta plataforma.</td></tr>';
        return;
    }

    motoristasListBody.innerHTML = motoristasPlataformaModal.map((item, index) => {
        return `
            <tr>
                <td style="font-weight: 600; color: #f8fafc;">${item.cidade}</td>
                <td style="color: #38bdf8;">${item.motorista}</td>
                <td style="text-align: right;">
                    <button type="button" class="btn-row-action" style="color: #38bdf8; margin-right: 12px;" onclick="editarMapeamentoModal(${index})">Editar</button>
                    <button type="button" class="btn-row-action" style="color: #ef4444;" onclick="deletarMapeamentoModal(${index})">Deletar</button>
                </td>
            </tr>
        `;
    }).join('');
}

async function salvarMapeamentoMotoristaModal(e) {
    e.preventDefault();
    if (!motCidadeSelect || !motNome) return;
    const cidade = motCidadeSelect.value.trim();
    const motorista = motNome.value.trim();
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : (platformSelector.value || "anjun");

    if (!cidade || !motorista) {
        alert("Selecione a cidade e informe o nome do motorista.");
        return;
    }

    const jaExiste = motoristasPlataformaModal.some(item =>
        item.cidade.toLowerCase() === cidade.toLowerCase() &&
        item.motorista.toLowerCase() === motorista.toLowerCase()
    );
    if (jaExiste) {
        alert(`O motorista "${motorista}" já está cadastrado para a cidade "${cidade}".`);
        return;
    }

    motoristasPlataformaModal.push({ cidade, motorista });

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: motoristasPlataformaModal, plataforma: platId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            motNome.value = '';
            renderizarListaMotoristasModal();
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

    const novoMotorista = prompt(`Editar nome do motorista para a cidade "${item.cidade}":`, item.motorista);
    if (novoMotorista === null) return;
    
    const novoMotoristaTrim = novoMotorista.trim();
    if (!novoMotoristaTrim) {
        alert("O nome do motorista não pode ser vazio.");
        return;
    }
    if (novoMotoristaTrim === item.motorista) return;

    const jaExiste = motoristasPlataformaModal.some((it, idx) =>
        idx !== index &&
        it.cidade.toLowerCase() === item.cidade.toLowerCase() &&
        it.motorista.toLowerCase() === novoMotoristaTrim.toLowerCase()
    );
    if (jaExiste) {
        alert(`O motorista "${novoMotoristaTrim}" já está cadastrado para a cidade "${item.cidade}".`);
        return;
    }

    item.motorista = novoMotoristaTrim;
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : (platformSelector.value || "anjun");

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: motoristasPlataformaModal, plataforma: platId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            renderizarListaMotoristasModal();
            await carregarConfiguracoes();
        } else {
            alert("Erro ao editar motorista: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

window.deletarMapeamentoModal = async (index) => {
    if (index < 0 || index >= motoristasPlataformaModal.length) return;
    const item = motoristasPlataformaModal[index];

    if (!confirm(`Deseja remover o motorista "${item.motorista}" da cidade "${item.cidade}"?`)) return;

    motoristasPlataformaModal.splice(index, 1);
    const platId = motoristaPlataformaSelect ? motoristaPlataformaSelect.value : (platformSelector.value || "anjun");

    try {
        const res = await fetch(`${API_URL}/salvar-motoristas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ motoristas: motoristasPlataformaModal, plataforma: platId })
        });
        const data = await res.json();
        if (data.status === 'sucesso') {
            renderizarListaMotoristasModal();
            await carregarConfiguracoes();
        } else {
            alert("Erro ao remover motorista: " + (data.mensagem || "Erro desconhecido"));
        }
    } catch (err) {
        alert("Falha ao comunicar com o servidor: " + err.message);
    }
};

// ----------------------------------------------------
// ABA CREDENCIAIS
// ----------------------------------------------------
function popularCredenciaisPlataformaModal() {
    if (!modalPlatSelector) return;
    const keys = Object.keys(todasPlataformas);
    if (keys.length === 0) {
        modalPlatSelector.innerHTML = '<option value="">Nenhuma plataforma cadastrada</option>';
        if (modalLoginUser) modalLoginUser.value = "";
        if (modalLoginPass) modalLoginPass.value = "";
    } else {
        modalPlatSelector.innerHTML = keys.map(key => `
            <option value="${key}">${todasPlataformas[key].nome}</option>
        `).join('');

        const platAtual = (platformSelector && platformSelector.value) || keys[0];
        modalPlatSelector.value = platAtual;
        carregarDadosPlataformaModal(platAtual);
    }
}

function carregarDadosPlataformaModal(platId) {
    const p = todasPlataformas[platId];
    if (p) {
        if (modalLoginUser) modalLoginUser.value = p.login_usuario || "";
        if (modalLoginPass) modalLoginPass.value = p.login_senha || "";
    } else {
        if (modalLoginUser) modalLoginUser.value = "";
        if (modalLoginPass) modalLoginPass.value = "";
    }
}

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

        const payload = {
            id: platId,
            login_usuario: modalLoginUser ? modalLoginUser.value.trim() : "",
            login_senha: modalLoginPass ? modalLoginPass.value.trim() : ""
        };

        btnModalSalvar.disabled = true;
        btnModalSalvar.innerText = "Salvando...";

        try {
            const res = await fetch(`${API_URL}/salvar-credenciais`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.status === 'sucesso') {
                alert(data.mensagem);
                if (todasPlataformas[platId]) {
                    todasPlataformas[platId].login_usuario = payload.login_usuario;
                    todasPlataformas[platId].login_senha = payload.login_senha;
                }
            } else {
                alert("Erro ao salvar: " + data.mensagem);
            }
        } catch (e) {
            console.error(e);
            alert("Erro ao conectar com o servidor.");
        } finally {
            btnModalSalvar.disabled = false;
            btnModalSalvar.innerText = "Salvar Credenciais";
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
                novaLinha.innerHTML = `
                    <td style="color: #64748b;">${horarioStr}</td>
                    <td style="font-family: monospace; cursor: pointer; transition: all 0.2s;" class="copyable-code" title="Clique para copiar (${bip.codigo})">${bip.codigo}</td>
                    <td title="${bip.cidade}">${bip.cidade}</td>
                    <td style="text-align: center;"><span class="status-badge ${badgeClass}">${statusText}</span></td>
                `;
                historyLog.appendChild(novaLinha);
            });
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
        const confirmar = confirm("Deseja realmente REINICIAR O SISTEMA?\n\nIsso fechará o navegador Chrome, encerrará processos travados e reiniciará o CMD/servidor automaticamente.");
        if (!confirmar) return;

        if (overlayReiniciando) {
            overlayReiniciando.style.display = 'flex';
        }

        try {
            await fetch(`${API_URL}/reiniciar-sistema`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (e) {
            console.log("[*] Servidor finalizando para reinício...");
        }

        // Aguarda 2 segundos para o processo antigo encerrar e novo iniciar
        await new Promise(r => setTimeout(r, 2000));

        let tentativas = 0;
        const maxTentativas = 30; // até 30 segundos
        const intervaloReconexao = setInterval(async () => {
            tentativas++;
            try {
                const res = await fetch(`${API_URL}/configuracoes?_=${Date.now()}`, { cache: 'no-store' });
                if (res.ok) {
                    clearInterval(intervaloReconexao);
                    if (overlayReiniciandoMsg) {
                        overlayReiniciandoMsg.innerText = "Servidor reiniciado com sucesso! Recarregando tela...";
                    }
                    setTimeout(() => {
                        window.location.reload();
                    }, 500);
                }
            } catch (err) {
                if (overlayReiniciandoMsg) {
                    overlayReiniciandoMsg.innerText = `Reiniciando o sistema e reconectando (${tentativas}s)...`;
                }
            }

            if (tentativas >= maxTentativas) {
                clearInterval(intervaloReconexao);
                if (overlayReiniciando) {
                    overlayReiniciando.style.display = 'none';
                }
                alert("O servidor demorou para responder. Verifique a janela do CMD ou pressione F5 para atualizar.");
            }
        }, 1000);
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

async function checarStatusLicenca() {
    try {
        const res = await fetch(`${API_URL}/status-licenca?_=${Date.now()}`);
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

        if (iconeStatusLicenca) iconeStatusLicenca.innerText = "🟢";
        if (textoStatusLicenca) textoStatusLicenca.innerText = `${lic.dias_restantes}d`;
        if (btnStatusLicenca) {
            btnStatusLicenca.classList.remove('licenca-alerta');
            btnStatusLicenca.title = `Licença Ativa: ${lic.cliente} (Válida até ${lic.expiracao} - ${lic.dias_restantes} dias restantes)`;
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

        if (btnFecharModalLicenca) btnFecharModalLicenca.style.display = 'block';

        // Reabilita controles de triagem caso estivessem bloqueados
        if (manualCodeInput) manualCodeInput.disabled = false;
        if (btnManualEnviar) btnManualEnviar.disabled = false;

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
        if (modalLicenca) modalLicenca.style.display = 'flex';

        // Trava inputs de triagem
        if (manualCodeInput) manualCodeInput.disabled = true;
        if (btnManualEnviar) btnManualEnviar.disabled = true;
    }
}

// Botão para abrir o modal de licença manualmente pelo topo
if (btnStatusLicenca) {
    btnStatusLicenca.addEventListener('click', () => {
        if (modalLicenca) {
            modalLicenca.style.display = 'flex';
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

                setTimeout(() => {
                    if (modalLicenca) modalLicenca.style.display = 'none';
                    if (feedbackAtivacaoMsg) feedbackAtivacaoMsg.style.display = 'none';
                    if (inputChaveLicenca) inputChaveLicenca.value = "";
                }, 1500);
            } else {
                if (feedbackAtivacaoMsg) {
                    feedbackAtivacaoMsg.style.display = 'block';
                    feedbackAtivacaoMsg.style.background = 'rgba(239, 68, 68, 0.2)';
                    feedbackAtivacaoMsg.style.color = '#f87171';
                    feedbackAtivacaoMsg.innerText = "✕ " + (data.mensagem || "Chave inválida!");
                }
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

// Checagem automática de novas versões na nuvem ao iniciar e periodicamente
async function checarAtualizacaoAutomatica() {
    try {
        const res = await fetch(`${API_URL}/checar-atualizacao?_=${Date.now()}`);
        const data = await res.json();
        if (data && data.sucesso) {
            if (data.versao_atual && badgeVersaoSistema) {
                badgeVersaoSistema.innerText = `v${data.versao_atual}`;
            }
            if (data.tem_atualizacao) {
                const querAtualizar = confirm(
                    `🚀 Uma nova atualização do Galpão Monitored está disponível!\n\n` +
                    `Versão: v${data.versao_nova}\n` +
                    `Novidades: ${data.descricao || 'Melhorias e correções gerais.'}\n\n` +
                    `Deseja baixar e aplicar a atualização agora automaticamente?`
                );
                if (querAtualizar && btnAplicarAtualizacao) {
                    btnAplicarAtualizacao.click();
                }
            }
        }
    } catch (e) {
        // Falha silenciosa em caso de oscilação de rede
    }
}
setTimeout(checarAtualizacaoAutomatica, 4500);
setInterval(checarAtualizacaoAutomatica, 30 * 60 * 1000);

