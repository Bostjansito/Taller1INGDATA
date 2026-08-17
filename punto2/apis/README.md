# Mini proyecto API-Football

Extracción y análisis de la Copa Mundial de Fútbol 2022 usando
API-Football (`league=1`, `season=2022`).

## Activar el entorno

Desde la carpeta `punto2`:

```bash
source /home/emanuel/Music/Miniconda/etc/profile.d/conda.sh
conda activate "/home/emanuel/Universidad/Sexto/Ingenieria de Datos/Taller1INGDATA/punto2/.venv"
```

El entorno usa Python 3.12. Debido a que la ruta contiene espacios, se
recomienda ejecutar las herramientas como módulos de Python.

## Flujo recomendado con notebooks

El proyecto está dividido en dos notebooks para separar responsabilidades:

1. `exploracion_extraccion.ipynb`: consulta o lee la caché, explora los JSON,
   normaliza los datos y genera los tres archivos Parquet.
2. `analisis.ipynb`: lee exclusivamente los Parquet y responde las preguntas
   del taller con tablas y visualizaciones.

```bash
cd "/home/emanuel/Universidad/Sexto/Ingenieria de Datos/Taller1INGDATA/punto2/apis"
python -m jupyter lab exploracion_extraccion.ipynb analisis.ipynb
```

## Alternativa mediante script

```bash
cd "/home/emanuel/Universidad/Sexto/Ingenieria de Datos/Taller1INGDATA/punto2/apis"
python extractor_api.py
```

La ejecución normal reutiliza los JSON de `cache/`. Para consultar nuevamente
la API, consumiendo cuota, se puede usar:

```bash
python extractor_api.py --actualizar
```

## Abrir el notebook

```bash
python -m jupyter lab exploracion_extraccion.ipynb analisis.ipynb
```

El notebook solo lee `equipos.parquet`, `partidos.parquet` y
`clasificacion.parquet`; no consulta la API.

## Recrear el entorno

Desde `punto2`, usando el archivo declarativo:

```bash
/home/emanuel/Music/Miniconda/bin/conda env create \
  --prefix ./.venv \
  --file ./apis/environment.yml
```

`requirements.txt` contiene el inventario con versiones exactas instalado en
el entorno utilizado para generar los entregables.
