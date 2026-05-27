// ============================================================
// SERVICE WORKER — Live Studio Dominó
// Estratégia: Cache-first para /static (vídeos, manifest).
//             Network-only para tudo que precisa ser fresco
//             (/obter_alerta, /audio, Firebase).
// ============================================================

const CACHE_NAME = 'domino-static-v1.01';

// Arquivos da /static que queremos pre-cachear na instalação
const ARQUIVOS_PARA_CACHEAR = [
    '/static/EH_Nois.mp4',
    '/static/DInovo.mp4',
    '/static/manifest.json',
    '/static/domino_logo.png',
];

// Prefixos/URLs que NUNCA devem vir do cache (sempre rede)
const SEMPRE_REDE = [
    '/obter_alerta',
    '/audio',
    '/radio-proxy',
    'firestore.googleapis.com',
];

// Rotas que o SW nunca deve interceptar (fetch events do próprio servidor Flask)
const IGNORAR_SW = [
    '/obter_alerta',
    '/audio',
    '/radio-proxy',
];

// ── INSTALL: baixa e armazena os estáticos ──────────────────
self.addEventListener('install', event => {
    console.log('[SW] Instalando e cacheando arquivos estáticos...');
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return Promise.allSettled(
                ARQUIVOS_PARA_CACHEAR.map(url =>
                    cache.add(url).catch(err =>
                        console.warn(`[SW] Não foi possível cachear ${url}:`, err)
                    )
                )
            );
        }).then(() => {
            console.log('[SW] Instalação concluída.');
            // Força este SW a assumir imediatamente sem esperar reload
            return self.skipWaiting();
        })
    );
});

// ── ACTIVATE: limpa caches antigos de versões anteriores ────
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(nomes => {
            return Promise.all(
                nomes
                    .filter(nome => nome !== CACHE_NAME)
                    .map(nome => {
                        console.log('[SW] Removendo cache antigo:', nome);
                        return caches.delete(nome);
                    })
            );
        }).then(() => self.clients.claim())
    );
});

// ── FETCH: intercepta requisições ───────────────────────────
self.addEventListener('fetch', event => {
    const url = event.request.url;

    // Rotas dinâmicas críticas → SW não intercepta de forma alguma
    // (deixa o browser fazer o fetch diretamente, evitando falhas de rede no SW)
    const ehDinamico = IGNORAR_SW.some(trecho => url.includes(trecho));
    if (ehDinamico) return;  // não chama event.respondWith → browser assume o controle

    // Demais rotas da rede → busca normalmente sem cache
    const ehRedeSimples = SEMPRE_REDE.some(trecho => url.includes(trecho));
    if (ehRedeSimples) {
        event.respondWith(fetch(event.request));
        return;
    }

    // Arquivos /static → Cache-first: serve do cache, atualiza em background
    if (url.includes('/static/')) {
        event.respondWith(
            caches.open(CACHE_NAME).then(async cache => {
                const cached = await cache.match(event.request);
                if (cached) {
                    // Serve do cache imediatamente
                    // Atualiza em background para próxima vez (stale-while-revalidate)
                    fetch(event.request).then(resp => {
                        if (resp && resp.status === 200)
                            cache.put(event.request, resp.clone());
                    }).catch(() => {});
                    return cached;
                }
                // Não estava no cache: busca na rede e armazena
                const resp = await fetch(event.request);
                if (resp && resp.status === 200)
                    cache.put(event.request, resp.clone());
                return resp;
            })
        );
        return;
    }

    // Qualquer outra rota (ex: /) → Network-first com fallback cache
    event.respondWith(
        fetch(event.request).catch(() => caches.match(event.request))
    );
});
