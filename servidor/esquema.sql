-- Tablas de BigQuery del servidor de "A mí me strofa".
-- Se crean una vez, a mano, al desplegar:
--   bq query --location=us-central1 --use_legacy_sql=false < servidor/esquema.sql

CREATE SCHEMA IF NOT EXISTS `a-mi-mestrofa.mestrofa`
OPTIONS (location = 'us-central1');

-- Una fila por día del blog, escrita UNA vez y nunca cambiada.
CREATE TABLE IF NOT EXISTS `a-mi-mestrofa.mestrofa.predicciones_qmp` (
  fecha          DATE      NOT NULL,  -- la entrada del blog
  pred_modelo    INT64     NOT NULL,  -- 1/2/3, mi modelo
  pred_gemini    INT64     NOT NULL,  -- 1/2/3, Gemini genérico
  prob_1         FLOAT64,
  prob_2         FLOAT64,
  prob_3         FLOAT64,
  predicho_el    TIMESTAMP NOT NULL,
  modelo_version STRING    NOT NULL,  -- qué campeón adivinó
  gemini_modelo  STRING    NOT NULL,
  huella         STRING    NOT NULL   -- sha256 del texto que se predijo
);

-- Un renglón por uso de la caja de texto: sirve para el tope diario.
CREATE TABLE IF NOT EXISTS `a-mi-mestrofa.mestrofa.usos_caja` (
  dia     DATE      NOT NULL,
  momento TIMESTAMP NOT NULL
)
PARTITION BY dia;
