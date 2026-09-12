"""Dónde se guardan las predicciones congeladas y la cuenta de usos de la caja.

Dos versiones con la misma forma:
    AlmacenMemoria   para los tests y para probar en local
    AlmacenBigQuery  el de verdad (esquema en servidor/esquema.sql)

Por qué BigQuery: es el almacén de datos del proyecto (PLAN, Bloque E). A este
tamaño entra en el tier gratis. Se escribe con DML (MERGE / INSERT), no con
streaming inserts, que se cobran aparte.
"""
from datetime import date, datetime, timezone


class AlmacenMemoria:
    def __init__(self):
        self._pred = {}
        self._usos = {}

    def predicciones(self):
        return dict(self._pred)

    def guardar(self, fila):
        """Guarda sólo si ese día no tenía predicción. Devuelve si guardó."""
        if fila["fecha"] in self._pred:
            return False
        self._pred[fila["fecha"]] = dict(fila)
        return True

    def usos(self, dia):
        return self._usos.get(dia, 0)

    def anotar_uso(self, dia):
        self._usos[dia] = self._usos.get(dia, 0) + 1


class AlmacenBigQuery:
    def __init__(self, proyecto, dataset):
        from google.cloud import bigquery
        self._bq = bigquery
        self._cliente = bigquery.Client(project=proyecto)
        self._pred = f"`{proyecto}.{dataset}.predicciones_qmp`"
        self._usos = f"`{proyecto}.{dataset}.usos_caja`"

    def _q(self, sql, **params):
        tipos = {str: "STRING", int: "INT64", float: "FLOAT64"}
        qp = []
        for k, v in params.items():
            if k in ("fecha", "dia"):
                qp.append(self._bq.ScalarQueryParameter(k, "DATE", date.fromisoformat(v)))
            elif k == "momento":
                momento = datetime.fromisoformat(v.replace("Z", "+00:00"))
                qp.append(self._bq.ScalarQueryParameter(k, "TIMESTAMP", momento))
            else:
                qp.append(self._bq.ScalarQueryParameter(k, tipos[type(v)], v))
        cfg = self._bq.QueryJobConfig(query_parameters=qp)
        job = self._cliente.query(sql, job_config=cfg)
        return job, list(job.result())

    def predicciones(self):
        # Si alguna vez entraron dos filas del mismo día, vale la primera.
        _, filas = self._q(f"""
            SELECT * FROM {self._pred}
            QUALIFY ROW_NUMBER() OVER (PARTITION BY fecha ORDER BY predicho_el) = 1""")
        return {
            r["fecha"].isoformat(): {
                "fecha": r["fecha"].isoformat(),
                "pred_modelo": r["pred_modelo"],
                "pred_gemini": r["pred_gemini"],
                "probs": [r["prob_1"], r["prob_2"], r["prob_3"]],
                "predicho_el": r["predicho_el"].astimezone(timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "modelo_version": r["modelo_version"],
                "gemini_modelo": r["gemini_modelo"],
                "huella": r["huella"],
            }
            for r in filas
        }

    def guardar(self, fila):
        p1, p2, p3 = fila["probs"]
        job, _ = self._q(f"""
            MERGE {self._pred} T
            USING (SELECT @fecha AS fecha) S
            ON T.fecha = S.fecha
            WHEN NOT MATCHED THEN INSERT
              (fecha, pred_modelo, pred_gemini, prob_1, prob_2, prob_3,
               predicho_el, modelo_version, gemini_modelo, huella)
            VALUES (@fecha, @pred_modelo, @pred_gemini, @p1, @p2, @p3,
                    @momento, @modelo_version, @gemini_modelo, @huella)""",
            fecha=fila["fecha"], pred_modelo=fila["pred_modelo"],
            pred_gemini=fila["pred_gemini"], p1=p1, p2=p2, p3=p3,
            momento=fila["predicho_el"], modelo_version=fila["modelo_version"],
            gemini_modelo=fila["gemini_modelo"], huella=fila["huella"])
        return (job.num_dml_affected_rows or 0) == 1

    def usos(self, dia):
        _, filas = self._q(f"SELECT COUNT(*) AS n FROM {self._usos} WHERE dia = @dia", dia=dia)
        return filas[0]["n"]

    def anotar_uso(self, dia):
        self._q(f"INSERT {self._usos} (dia, momento) VALUES (@dia, @momento)",
                dia=dia, momento=datetime.now(timezone.utc).isoformat())
