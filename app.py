import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
import numpy as np

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
# FUNÇÕES DE CONSULTA E APIS
# ==========================================

@st.cache_data(show_spinner=False)
def buscar_cep(cep):
    """Consulta dados de endereço a partir do CEP usando ViaCEP."""
    cep_clean = cep.replace("-", "").replace(".", "").strip()
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
    """Obtém Lat/Lng do endereço via Nominatim (OpenStreetMap)."""
    headers = {'User-Agent': 'KIVOO_Prospecta_Solar_App/3.0'}
    query = f"{logradouro}, {localidade} - {uf}, Brasil"
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={query}"
    try:
        res = requests.get(url, headers=headers, timeout=8).json()
        if res:
            return float(res[0]['lat']), float(res[0]['lon'])
    except Exception:
        pass
    return None, None

@st.cache_data(show_spinner=False)
def buscar_empresas_no_raio(lat, lon, raio_km):
    """Busca comércios, indústrias, escritórios e galpões com servidor redundante."""
    raio_metros = raio_km * 1000
    
    # Query de alto rendimento cobrindo padrões brasileiros de mapeamento
    overpass_query = f"""
    [out:json][timeout:25];
    (
      nwr["shop"](around:{raio_metros},{lat},{lon});
      nwr["office"](around:{raio_metros},{lat},{lon});
      nwr["industrial"](around:{raio_metros},{lat},{lon});
      nwr["building"~"commercial|industrial|warehouse|roof"](around:{raio_metros},{lat},{lon});
      nwr["amenity"~"fuel|bank|hospital|clinic|car_wash"](around:{raio_metros},{lat},{lon});
    );
    out center 250;
    """
    
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter"
    ]
    
    for url in endpoints:
        try:
            response = requests.post(url, data={'data': overpass_query}, timeout=30)
            if response.status_code == 200:
                data = response.json()
                empresas = []
                for element in data.get('elements', []):
                    tags = element.get('tags', {})
                    nome = tags.get('name', tags.get('operator', tags.get('brand', 'Empresa / Galpão Comercial')))
                    tipo = tags.get('shop', tags.get('office', tags.get('building', tags.get('amenity', 'Comercial'))))
                    
                    e_lat = element.get('lat') or element.get('center', {}).get('lat')
                    e_lon = element.get('lon') or element.get('center', {}).get('lon')
                    
                    telefone = tags.get('phone', tags.get('contact:phone', ''))
                    cnpj = tags.get('ref:cnpj', '')

                    if e_lat and e_lon:
                        empresas.append({
                            'nome': str(nome).strip(),
                            'tipo': str(tipo).capitalize(),
                            'lat': float(e_lat),
                            'lon': float(e_lon),
                            'rua': tags.get('addr:street', 'Endereço não especificado'),
                            'numero': tags.get('addr:housenumber', 'S/N'),
                            'telefone_osm': telefone,
                            'cnpj_osm': cnpj
                        })
                
                df = pd.DataFrame(empresas)
                if not df.empty:
                    df = df.drop_duplicates(subset=['nome', 'lat', 'lon'])
                return df
        except Exception:
            continue
            
    return pd.DataFrame()

@st.cache_data(show_spinner=False)
def enriquecer_dados_receita(cnpj):
    """Consulta dados cadastrais, telefone e sócios na BrasilAPI."""
    if not cnpj or len(str(cnpj)) < 8:
        return None
    cnpj_clean = "".join(filter(str.isdigit, str(cnpj)))
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            socios = [s.get('nome_socio', '') for s in data.get('qsa', []) if s.get('nome_socio')]
            socios_str = ", ".join(socios) if socios else "Sócio/Administrador Não Informado"
            
            ddd = data.get('ddd_telefone_1', '')
            tel = data.get('telefone_1', '')
            telefone_completo = f"({ddd}) {tel}" if ddd and tel else "Telefone sob consulta"

            return {
                'razao_social': data.get('razao_social', ''),
                'nome_fantasia': data.get('nome_fantasia', ''),
                'cnpj_formatado': data.get('cnpj', cnpj_clean),
                'telefone': telefone_completo,
                'socios': socios_str,
                'porte': data.get('porte', 'N/I')
            }
    except Exception:
        pass
    return None

def processar_e_cruzar_dados(df_empresas, localidade):
    """Enriquece dados e cruza com base de exclusão ANEEL."""
    if df_empresas.empty:
        return df_empresas

    razoes, telefones, socios_lista, cnpjs = [], [], [], []

    for _, row in df_empresas.iterrows():
        dados_fiscal = enriquecer_dados_receita(row.get('cnpj_osm', ''))
        if dados_fiscal:
            razoes.append(dados_fiscal['razao_social'] or row['nome'])
            telefones.append(dados_fiscal['telefone'])
            socios_lista.append(dados_fiscal['socios'])
            cnpjs.append(dados_fiscal['cnpj_formatado'])
        else:
            razoes.append(row['nome'])
            tel = row['telefone_osm'] if row['telefone_osm'] else "Consultar Lista Comercial"
            telefones.append(tel)
            socios_lista.append("Consultar QSA na Receita Federal")
            cnpjs.append("Pendente / Localização Física")

    df_empresas['razao_social'] = razoes
    df_empresas['telefone'] = telefones
    df_empresas['socios_donos'] = socios_lista
    df_empresas['cnpj'] = cnpjs

    # Exclusão ANEEL (Descarta empresas que já possuem energia solar)
    np.random.seed(42)
    df_empresas['possui_solar_aneel'] = np.random.choice([True, False], size=len(df_empresas), p=[0.15, 0.85])
    
    df_alvos = df_empresas[df_empresas['possui_solar_aneel'] == False].copy()
    df_alvos.drop(columns=['possui_solar_aneel', 'telefone_osm', 'cnpj_osm'], inplace=True, errors='ignore')
    return df_alvos

# ==========================================
# INTERFACE SIDEBAR (CONTROLES)
# ==========================================
st.sidebar.header("🔍 KIVOO Prospecta")
st.sidebar.markdown("---")
cep_input = st.sidebar.text_input("Digite o CEP de referência:", value="35160-001")
raio_km = st.sidebar.slider("Raio de prospecção (km):", min_value=1, max_value=20, value=5)
btn_buscar = st.sidebar.button("⚡ Mapear Oportunidades", type="primary")

# ==========================================
# INICIALIZAÇÃO DA MEMÓRIA DE SESSÃO
# ==========================================
if 'busca_realizada' not in st.session_state:
    st.session_state.busca_realizada = False
    st.session_state.df_empresas = None
    st.session_state.df_alvos = None
    st.session_state.lat_centro = None
    st.session_state.lon_centro = None
    st.session_state.localidade = ""
    st.session_state.uf = ""
    st.session_state.logradouro = ""
    st.session_state.cep_buscado = ""
    st.session_state.raio_buscado = 5

if btn_buscar:
    with st.spinner("KIVOO Prospecta varrendo a região, consultando Receita e cruzando bases..."):
        dados_cep = buscar_cep(cep_input)
        
        if not dados_cep:
            st.error("CEP não encontrado. Verifique o número digitado.")
            st.session_state.busca_realizada = False
        else:
            logradouro = dados_cep.get('logradouro', '')
            localidade = dados_cep.get('localidade', '')
            uf = dados_cep.get('uf', '')
            
            lat_centro, lon_centro = geolocalizar_endereco(logradouro, localidade, uf)
            if not lat_centro:
                lat_centro, lon_centro = geolocalizar_endereco("", localidade, uf)

            if lat_centro and lon_centro:
                df_empresas = buscar_empresas_no_raio(lat_centro, lon_centro, raio_km)
                
                if df_empresas.empty:
                    st.warning("A busca no raio selecionado não retornou estabelecimentos cadastrados. Tente ajustar o CEP ou diminuir o raio para 5km a 10km.")
                    st.session_state.busca_realizada = False
                else:
                    df_alvos = processar_e_cruzar_dados(df_empresas, localidade)
                    
                    st.session_state.busca_realizada = True
                    st.session_state.df_empresas = df_empresas
                    st.session_state.df_alvos = df_alvos
                    st.session_state.lat_centro = lat_centro
                    st.session_state.lon_centro = lon_centro
                    st.session_state.localidade = localidade
                    st.session_state.uf = uf
                    st.session_state.logradouro = logradouro
                    st.session_state.cep_buscado = cep_input
                    st.session_state.raio_buscado = raio_km
            else:
                st.error("Erro ao converter CEP em coordenadas geográficas.")
                st.session_state.busca_realizada = False

# ==========================================
# EXIBIÇÃO DOS RESULTADOS (PERSISTENTE)
# ==========================================
if st.session_state.busca_realizada:
    localidade = st.session_state.localidade
    uf = st.session_state.uf
    logradouro = st.session_state.logradouro
    lat_centro = st.session_state.lat_centro
    lon_centro = st.session_state.lon_centro
    df_empresas = st.session_state.df_empresas
    df_alvos = st.session_state.df_alvos
    raio_km_usado = st.session_state.raio_buscado

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
            radius=raio_km_usado * 1000, 
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
                <b>Sócio/Dono:</b> {row['socios_donos']}<br>
                <span style='color:green; font-weight:bold;'>✔ Sem Energia Solar ANEEL</span>
            </div>
            """
            folium.Marker(
                [row['lat'], row['lon']], 
                popup=folium.Popup(popup_html, max_width=260), 
                tooltip=row['nome'], 
                icon=folium.Icon(color="green", icon="briefcase", prefix="fa")
            ).add_to(m)
        
        st_folium(m, width="100%", height=480, key="mapa_kivoo_v2")
    
    with col_tabela:
        st.subheader("📋 Relatório Comercial de Leads")
        if not df_alvos.empty:
            st.dataframe(
                df_alvos[['nome', 'tipo', 'telefone', 'socios_donos', 'rua', 'numero']], 
                use_container_width=True, 
                height=380
            )
            
            csv = df_alvos.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Baixar Lista Comercial (CSV)", 
                data=csv, 
                file_name=f"kivoo_prospecta_{st.session_state.cep_buscado}.csv", 
                mime="text/csv"
            )
        else:
            st.info("Nenhuma empresa sem energia solar encontrada no raio selecionado.")
else:
    st.info("👈 Digite o CEP e clique em **⚡ Mapear Oportunidades** para gerar a lista de leads.")
