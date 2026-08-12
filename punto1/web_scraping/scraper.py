import re
from datetime import datetime
from time import sleep
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import pandas as pd

EXTRAIDO_POR = "PerezQuintero"
BASE_URL = "https://books.toscrape.com/"

RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def parse_precio(texto):
    match = re.search(r'([^\d]*)([\d.,]+)', texto)
    simbolo = match.group(1).strip()
    valor = float(match.group(2).replace(',', ''))
    monedas = {"£": "GBP", "$": "USD", "€": "EUR"}
    moneda = monedas.get(simbolo, simbolo)
    return moneda, valor


def extraer_libro(driver, url_libro, categoria):
    driver.get(url_libro)
    sleep(0.5)
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    titulo = soup.find('h1').get_text(strip=True)

    tabla = soup.find('table', {'class': 'table table-striped'})
    filas = tabla.find_all('tr')
    info = {f.find('th').get_text(strip=True): f.find('td').get_text(strip=True) for f in filas}

    desc_tag = soup.find('div', {'id': 'product_description'})
    descripcion = desc_tag.find_next_sibling('p').get_text(strip=True) if desc_tag else ""

    rating_tag = soup.find('p', class_='star-rating')
    rating_texto = rating_tag['class'][1] if rating_tag else None
    calificacion = RATING_MAP.get(rating_texto)

    img_tag = soup.find('div', class_='item active').find('img')
    url_imagen = urljoin(url_libro, img_tag['src'])

    moneda, precio_sin_impuesto = parse_precio(info.get('Price (excl. tax)', ''))
    _, precio_con_impuesto = parse_precio(info.get('Price (incl. tax)', ''))
    _, impuesto = parse_precio(info.get('Tax', ''))

    disponibilidad = info.get('Availability', '')
    stock_match = re.search(r'(\d+)\s+available', disponibilidad)
    cantidad_stock = int(stock_match.group(1)) if stock_match else 0

    cantidad_resenas = int(info.get('Number of reviews', 0))

    return {
        "upc": info.get('UPC'),
        "titulo": titulo,
        "categoria": categoria,
        "descripcion": descripcion,
        "tipo_producto": info.get('Product Type'),
        "precio_sin_impuesto": precio_sin_impuesto,
        "precio_con_impuesto": precio_con_impuesto,
        "impuesto": impuesto,
        "moneda": moneda,
        "disponibilidad": disponibilidad,
        "cantidad_stock": cantidad_stock,
        "calificacion": calificacion,
        "cantidad_resenas": cantidad_resenas,
        "url_libro": url_libro,
        "url_imagen": url_imagen,
        "fecha_extraccion": datetime.now(),
        "extraido_por": EXTRAIDO_POR,
    }


def obtener_urls_libros_categoria(driver, url_categoria):
    urls = []
    url_actual = url_categoria
    while True:
        driver.get(url_actual)
        sleep(1)
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        links = soup.select('h3 a')
        for a in links:
            urls.append(urljoin(url_actual, a['href']))

        siguiente = soup.select_one('li.next a')
        if siguiente:
            url_actual = urljoin(url_actual, siguiente['href'])
        else:
            break
    return urls


service = Service('/usr/bin/chromedriver')
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=service, options=options)

# --- Categorías ---
driver.get(BASE_URL)
sleep(2)
soup = BeautifulSoup(driver.page_source, 'html.parser')
categorias_links = soup.select('div.side_categories ul li ul li a')

categorias_info = []
for a in categorias_links:
    nombre = a.get_text(strip=True)
    url_categoria = urljoin(BASE_URL, a['href'])
    categorias_info.append({"categoria": nombre, "url_categoria": url_categoria})

categorias_data = []
for cat in categorias_info:
    driver.get(cat["url_categoria"])
    sleep(1)
    cat_soup = BeautifulSoup(driver.page_source, 'html.parser')
    texto_pagina = cat_soup.get_text()
    match = re.search(r'(\d+)\s+results?', texto_pagina)
    cantidad_libros = int(match.group(1)) if match else None

    categorias_data.append({
        "categoria": cat["categoria"],
        "url_categoria": cat["url_categoria"],
        "cantidad_libros": cantidad_libros,
        "fecha_extraccion": datetime.now(),
        "extraido_por": EXTRAIDO_POR,
    })
    print(cat["categoria"], "->", cantidad_libros, "libros")

df_categorias = pd.DataFrame(categorias_data)
df_categorias.to_parquet("categorias.parquet", index=False)
print("categorias.parquet guardado con", len(df_categorias), "filas.")

# --- Libros ---
libros_data = []
for cat in categorias_info:
    urls_libros = obtener_urls_libros_categoria(driver, cat["url_categoria"])
    print(f"{cat['categoria']}: {len(urls_libros)} libros encontrados")
    for url_libro in urls_libros:
        datos_libro = extraer_libro(driver, url_libro, cat["categoria"])
        libros_data.append(datos_libro)

df_libros = pd.DataFrame(libros_data)
df_libros.to_parquet("libros.parquet", index=False)
print("libros.parquet guardado con", len(df_libros), "filas.")

driver.quit()
print("Proceso completo.")