# Cómo abrir el reporte de Power BI

Esta guía es para abrir el proyecto de Power BI en tu computador, actualizarlo contra Snowflake y tomar las capturas de cada página. El archivo no incluye usuario ni contraseña. Esas credenciales las pides Power BI Desktop en el primer refresh.

El proyecto está en formato PBIP: un archivo `.pbip`, una carpeta `InsurancePortfolio.SemanticModel` (modelo en TMDL) y una carpeta `InsurancePortfolio.Report` (reporte en PBIR).

## 1. Descargar y descomprimir

1. Entra al repositorio privado y descarga el zip `powerbi/InsurancePortfolio-PBIP.zip`, o clona el repositorio y entra a la carpeta `powerbi`.
2. Si descargaste el zip, descomprímelo en una carpeta local, por ejemplo `Documentos\InsurancePortfolio`.
3. Debes ver estos elementos al mismo nivel:
   - `InsurancePortfolio.pbip`
   - `InsurancePortfolio.SemanticModel`
   - `InsurancePortfolio.Report`
   - `EXPECTED_NUMBERS.md` (lista de totales esperados)
   - `LEEME.md` (esta guía, si viene dentro del zip)

No abras un `.pbix`. Este proyecto se abre con el archivo `.pbip`.

## 2. Abrir el proyecto en Power BI Desktop

1. Abre Power BI Desktop en Windows.
2. Si tu versión es anterior a la que ya trae PBIP y PBIR activados por defecto, ve a **Archivo > Opciones y configuración > Opciones > Características de vista previa** y activa el almacenamiento de informes en formato PBIR (o Power BI Project / PBIP, según el nombre que muestre tu versión). Cierra y vuelve a abrir Desktop.
3. En el Explorador de archivos, haz doble clic en `InsurancePortfolio.pbip`, o en Desktop usa **Archivo > Abrir** y elige ese archivo.
4. Espera a que cargue el modelo y las tres páginas: **Portfolio Overview**, **Risk Drivers** y **Data Quality**.

Si Desktop pide actualizar un formato o aplicar un cambio de esquema, acepta y guarda una copia en la misma carpeta.

## 3. Credenciales de Snowflake y actualización

La conexión ya está definida, sin contraseña, con estos valores:

- Servidor: `wngvror-ly04177.snowflakecomputing.com`
- Warehouse: `COMPUTE_WH`
- Base de datos: `INSURANCE_PORTFOLIO`
- Esquema: `MARTS`
- Rol: `INSURANCE_PBI_READONLY`
- Modo: Import

Pasos:

1. En la cinta, pulsa **Actualizar** (Refresh).
2. Cuando Desktop pida credenciales de Snowflake, elige autenticación con usuario y contraseña.
3. Escribe tu usuario y tu contraseña de Snowflake. No cambies el servidor ni el warehouse si aparecen prellenados.
4. Si te pregunta el rol, usa `INSURANCE_PBI_READONLY`.
5. Confirma y espera a que termine la importación. Hay unas 678,013 pólizas en varias tablas. En un warehouse X-Small puede tardar unos minutos.

Las credenciales quedan guardadas en tu computador, no en los archivos del proyecto. No copies `localSettings.json` ni `cache.abf` de la carpeta `.pbi` al repositorio.

## 4. Revisar los números y tomar capturas

1. Abre `EXPECTED_NUMBERS.md` o `docs/powerbi_expected_numbers.md` en el repositorio.
2. En la página **Portfolio Overview**, comprueba los KPI: 678,013 pólizas, 358,499.45 de exposición, 36,102 siniestros, frecuencia 0.100703, severidad media 2,265.51, prima pura 167.11, 5.02% de pólizas con siniestro y 59,909,216.50 de importe emparejado.
3. En **Risk Drivers**, revisa las barras por edad del conductor, edad del vehículo, potencia, área, región y bonus-malus. En la tabla inferior, las pólizas de vehículo nuevo (edad 0) deben mostrar un hueco grande entre Claim Count y Matched Severity Rows.
4. En **Data Quality**, comprueba los controles de calidad de la lista (9,116 pólizas sin severidad, 195 filas huérfanas, 496 duplicados, 1,224 exposiciones mayores a 1, y que los dos importes emparejados coincidan en 59,909,216.50).
5. Toma una captura de pantalla de cada una de las tres páginas, a página completa, con los filtros en el nivel del libro (sin filtros extra).

## Si algo falla al abrir el reporte

El modelo semántico (tablas, relaciones y medidas DAX) está en TMDL y sigue el esquema documentado. El reporte está en PBIR, que es el formato actual, pero un archivo generado fuera de Windows puede ser más frágil que uno guardado por Desktop.

- Si el `.pbip` no abre, actualiza Power BI Desktop e activa la característica de vista previa de PBIP o PBIR. Luego vuelve a abrir el archivo.
- Si el modelo carga y las medidas aparecen en el panel de datos, pero alguna visual no se dibuja, no borres el modelo. Recrea esa visual a mano con las mismas medidas. La guía de diseño está en `docs/power_bi_design.md`.
- Si el refresh falla por permisos, confirma que tu usuario tiene el rol `INSURANCE_PBI_READONLY` y que ese rol puede leer `INSURANCE_PORTFOLIO.MARTS`. El rol no debe leer `RAW`.
- Si el refresh pide un servidor distinto, no lo cambies. El parámetro `SnowflakeServer` ya apunta a `wngvror-ly04177.snowflakecomputing.com`.
- No hay tabla de fechas a propósito. El origen no trae fechas de póliza ni de siniestro, y no se inventaron.
- `MART_RISK_SEGMENTS` está desconectada a propósito. No la uses en los mismos visuales que las medidas oficiales.

Después del primer refresh exitoso, puedes guardar el proyecto. Si Desktop genera un `.pbix` de respaldo, no es necesario subirlo al repositorio.
