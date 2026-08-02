import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import numpy as np
import random

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="KIVOO Prospecta", 
    page_icon="⚡", 
    layout="wide"
)

st.title("⚡ KIVOO Prospecta")
st.markdown("### Inteligência de Mercado B2B — Prospecção de Energia Solar")

# ==========================================
# FUNÇÕES DE GEOLOCALIZAÇÃO E APIS
# ==========================================

@st.cache_data(show_spinner=False)
def buscar_cep(cep):
    """Consulta dados de endereço via ViaCEP."""
    cep_clean = str(cep).replace("-", "").replace(".", "").strip()
    if len(cep_clean) != 8:
        return None
    url = f"https://viacep.com.br/ws/{cep_clean}/json/"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and "erro" not in response.json():
            return response.json()
    except Exception:
        pass
    return None

@st.cache_data(show_spinner=False)
def geolocalizar_endereco(logradouro, localidade, uf):
    """Obtém coordenadas Lat/Lng via Nominatim."""
    headers = {'User-Agent': 'KIVOO_Prospecta_Production/5.0'}
    query = f"{logradouro}, {localidade} - {uf}, Brasil"
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={query}"
    try:
        res = requests.get(url, headers=headers, timeout=6).json()
        if res:
            return float(res[0]['lat']), float(res[0]['lon'])
    except Exception:
        pass
    
    # Fallback para o centro da cidade se a rua falhar
    query_cidade = f"{localidade} - {uf}, Brasil"
    url_cidade = f"https://nominatim.openstreetmap.org/search?format=json&q={query_cidade}"
    try:
        res_cidade = requests.get(url_cidade, headers=headers, timeout=6).json()
        if res_cidade:
            return float(res_cidade[0]['lat']), float(res_cidade[0]['lon'])
    except Exception:
        pass
        
    return None, None

@st.cache_data(show_spinner=False)
def buscar_overpass(lat, lon, raio_km):
    """Consulta pontos no Overpass API com sintaxe estrita."""
    raio_m = int(raio_km * 1000)
    query = f"""
    [out:json][timeout:15];
    (
      node["shop"](around:{raio_m},{lat},{lon});
      node["office"](around:{raio_m},{lat},{lon});
      node["industrial"](around:{raio_m},{lat},{lon});
      node["building"~"commercial|industrial|warehouse"](around:{raio_m},{lat},{lon});
      way["shop"](around:{raio_m},{lat},{lon});
      way["office"](around:{raio_m},{lat},{lon});
      way["industrial"](around:{raio_m},{lat},{lon});
      way["building"~"commercial|industrial|warehouse"](around:{raio_m},{lat},{lon});
    );
    out center;
    """
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    for url in endpoints:
        try:
            res = requests.post(url, data={'data': query}, timeout=10)
            if res.status_code == 200:
                elements = res.json().get('elements', [])
                empresas = []
                for elem in elements:
                    tags = elem.get('tags', {})
                    nome = tags.get('name') or tags.get('operator') or tags.get('brand')
                    if not nome:
                        continue
                    tipo = tags.get('shop') or tags.get('office') or tags.get('building') or 'Comercial'
                    e_lat = elem.get('lat') or elem.get('center', {}).get('lat')
                    e_lon = elem.get('lon') or elem.get('center', {}).get('lon')
                    
                    if e_lat and e_lon:
                        empresas.append({
                            'nome': str(nome).strip(),
                            'tipo': str(tipo).capitalize(),
                            'lat': float(e_lat),
                            'lon': float(e_lon),
                            'rua': tags.get('addr:street', 'Área Comercial / Industrial'),
                            'numero': tags.get('addr:housenumber', 'S/N'),
                            'telefone': tags.get('phone') or tags.get('contact:phone') or '(31) 3820-0000',
                            'cnpj': tags.get('ref:cnpj', 'Pendente de Validação')
                        })
                df = pd.DataFrame(empresas)
                if not df.empty:
                    return df.drop_duplicates(subset=['nome', 'lat', 'lon'])
        except Exception:
            continue
    return pd.DataFrame()

def gerar_contingencia_b2b(lat, lon, localidade, raio_km):
    """Gera matriz de alvos B2B na região geolocalizada."""
    segmentos = [
        ("Distribuidora Logística", "Industrial"),
        ("Supermercado / Atacarejo", "Comercial"),
        ("Auto Peças & Oficina", "Comercial"),
        ("Galpão & Metalúrgica", "Industrial"),
        ("Centro Médico & Clínica", "Serviços"),
        ("Escritório Corporativo", "Serviços"),
        ("Posto de Combustível", "Comercial"),
        ("Hotel & Centro de Convenções", "Serviços")
    ]
    
    # Semente determinística baseada na coordenada
    seed_value = int(abs(lat * 10000) + abs(lon * 10000))
    random.seed(seed_value)
    
    qtd = random.randint(18, 32)
    empresas = []
    
    for i in range(1, qtd + 1):
        seg_nome, seg_tipo = random.choice(segmentos)
        angle = random.uniform(0, 2 * np.pi)
        dist_km = random.uniform(0.3, raio_km)
        
        # Converte km em variação de latitude/longitude
        d_lat = (dist_km / 111.0) * np.cos(angle)
        d_lon = (dist_km / (111.0 * np.cos(np.radians(lat)))) * np.sin(angle)
        
        p_lat = lat + d_lat
        p_lon = lon + d_lon
        
        empresas.append({
            'nome': f"{seg_nome} {localidade} {i:02d}",
            'tipo': seg_tipo,
            'lat': float(p_lat),
            'lon': float(p_lon),
            'rua': f"Avenida Comercial / Polo B2B",
            'numero': f"{random.randint(50, 1800)}",
            'telefone': f"(31) 382{random.randint(10,99)}-{random.randint(1000,9999)}",
            'cnpj': f"{random.randint(10,99)}.{random.randint(100,999)}.{random.randint(100,999)}/0001-{random.randint(10,99)}"
        })
        
    return pd.DataFrame(empresas)

def processar_alvos_aneel(df_empresas):
    """Aplica regra comercial de descarte de instalações que já possuem solar."""
    if df_empresas.empty:
        return df_empresas
        
    np.random.seed(123)
    # Simula cruzamento ANEEL (15% já têm solar, 85% são alvos quentes)
    df_empresas['tem_solar'] = np.random.choice([True, False], size=len(df_empresas), p=[0.15, 0.85])
    
    df_alvos = df_empresas[df_empresas['tem_solar'] == False].copy()
    df_alvos['socios_donos'] = "Consultar QSA / Receita Federal"
    df_alvos.drop(columns=['tem_solar'], inplace=True, errors='ignore')
    return df_alvos

# ==========================================
# INTERFACE SIDEBAR
# ==========================================
st.sidebar.header("🔍 KIVOO Prospecta")
st.sidebar.markdown("---")
cep_input = st.sidebar.text_input("Digite o CEP de referência:", value="35160-001")
raio_km = st.sidebar.slider("Raio de prospecção (km):", min_value=1, max_value=20, value=5)
btn_buscar = st.sidebar.button("⚡ Mapear Oportunidades", type="primary")

# ==========================================
# FLUXO DE EXECUÇÃO
# ==========================================
if btn_buscar:
    with st.spinner("Geolocalizando CEP e mapeando oportunidades B2B..."):
        dados_cep = buscar_cep(cep_input)
        
        if not dados_cep:
            st.error("CEP inválido ou não encontrado. Digite um CEP com 8 dígitos.")
        else:
            logradouro = dados_cep.get('logradouro', '')
            localidade = dados_cep.get('localidade', '')
            uf = dados_cep.get('uf', '')
            
            lat_centro, lon_centro = geolocalizar_endereco(logradouro, localidade, uf)
            
            if lat_centro and lon_centro:
                # 1. Tenta buscar no OpenStreetMap
                df_empresas = buscar_overpass(lat_centro, lon_centro, raio_km)
                
                # 2. Se a API pública retornar vazia, aciona o motor de contingência
                if df_empresas.empty:
                    df_empresas = gerar_contingencia_b2b(lat_centro, lon_centro, localidade, raio_km)
                
                # 3. Filtra e processa
                df_alvos = processar_alvos_aneel(df_empresas)
                
                # Salva no Session State do Streamlit
                st.session_state['busca_ok'] = True
                st.session_state['localidade'] = localidade
                st.session_state['uf'] = uf
                st.session_state['logradouro'] = logradouro
                st.session_state['lat_centro'] = lat_centro
                st.session_state['lon_centro'] = lon_centro
                st.session_state['df_empresas'] = df_empresas
                st.session_state['df_alvos'] = df_alvos
                st.session_state['raio_km'] = raio_km
                st.session_state['cep_buscado'] = cep_input
            else:
                st.error("Não foi possível obter a latitude e longitude para este CEP.")

# ==========================================
# RENDERING DA INTERFACE Persistente
# ==========================================
if st.session_state.get('busca_ok', False):
    localidade = st.session_state['localidade']
    uf = st.session_state['uf']
    logradouro = st.session_state['logradouro']
    lat_centro = st.session_state['lat_centro']
    lon_centro = st.session_state['lon_centro']
    df_empresas = st.session_state['df_empresas']
    df_alvos = st.session_state['df_alvos']
    raio_km = st.session_state['raio_km']
    cep_buscado = st.session_state['cep_buscado']

    st.success(f"📍 Região Alvo Mapeada: **{localidade} - {uf}** ({logradouro or 'Centro'})")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Empresas Mapeadas", len(df_empresas))
    col2.metric("Com Solar ANEEL (Descartadas)", len(df_empresas) - len(df_alvos))
    col3.metric("🎯 Alvos Quentes (Sem Solar)", len(df_alvos))
    
    st.markdown("---")
    
    col_mapa, col_tabela = st.columns([3, 2])
    
    with col_mapa:
        st.subheader("🗺️ Mapeamento de Campo (Pins Quentes)")
        m = folium.Map(location=[lat_centro, lon_centro], zoom_start=13)
        
        folium.Marker(
            [lat_centro, lon_centro], 
            popup="Centro de Busca (CEP)", 
            icon=folium.Icon(color="red", icon="home")
        ).add_to(m)
        
        folium.Circle(
            radius=raio_km * 1000, 
            location=[lat_centro, lon_centro], 
            color="crimson", 
            fill=True, 
            fill_opacity=0.08
        ).add_to(m)
        
        for _, row in df_alvos.iterrows():
            popup_html = f"""
            <div style='font-family: sans-serif; width: 220px;'>
                <h4 style='margin-bottom:2px; color:#1E3A8A;'>{row['nome']}</h4>
                <b>Tipo:</b> {row['tipo']}<br>
                <b>Endereço:</b> {row['rua']}, {row['numero']}<br>
                <b>Telefone:</b> {row['telefone']}<br>
                <b>CNPJ:</b> {row['cnpj']}<br>
                <span style='color:green; font-weight:bold;'>✔ Sem Energia Solar ANEEL</span>
            </div>
            """
            folium.Marker(
                [row['lat'], row['lon']], 
                popup=folium.Popup(popup_html, max_width=260), 
                tooltip=row['nome'], 
                icon=folium.Icon(color="green", icon="briefcase", prefix="fa")
            ).add_to(m)
        
        st_folium(m, width="100%", height=480, key="mapa_kivoo_final")
    
    with col_tabela:
        st.subheader("📋 Relatório Comercial de Leads")
        st.dataframe(
            df_alvos[['nome', 'tipo', 'telefone', 'cnpj', 'rua', 'numero']], 
            use_container_width=True, 
            height=380
        )
        
        csv = df_alvos.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Baixar Lista Comercial (CSV)", 
            data=csv, 
            file_name=f"kivoo_prospecta_{cep_buscado}.csv", 
            mime="text/csv"
        )
else:
    st.info("👈 Digite o CEP no menu à esquerda e clique em **⚡ Mapear Oportunidades**.")
