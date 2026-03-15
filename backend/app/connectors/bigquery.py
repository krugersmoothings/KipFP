"""BigQuery connector for PetBooking pet days and revenue data.

Reads from the `petbooking-com-au.pbp_petbooking_prod` dataset using a
Google service account key provided via the BIGQUERY_SERVICE_ACCOUNT_JSON
environment variable.
"""

import json
import logging
import os

from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

PROJECT = "petbooking-com-au"
DATASET = "pbp_petbooking_prod"
FQ = f"`{PROJECT}.{DATASET}`"


class BigQueryAuthError(Exception):
    pass


class BigQueryClient:
    def __init__(self):
        sa_key_file = os.getenv("BIGQUERY_SA_KEY_FILE")
        sa_json = os.getenv("BIGQUERY_SERVICE_ACCOUNT_JSON")

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]

        if sa_key_file and os.path.isfile(sa_key_file):
            credentials = service_account.Credentials.from_service_account_file(
                sa_key_file, scopes=scopes,
            )
        elif sa_json:
            credentials = service_account.Credentials.from_service_account_info(
                json.loads(sa_json), scopes=scopes,
            )
        else:
            raise BigQueryAuthError(
                "Set BIGQUERY_SA_KEY_FILE or BIGQUERY_SERVICE_ACCOUNT_JSON"
            )
        self.client = bigquery.Client(project=PROJECT, credentials=credentials)

    def get_pet_days(self, date_from: str, date_to: str) -> list[dict]:
        """Daily pet days by property and service type.

        Parameters
        ----------
        date_from, date_to : str
            YYYY-MM-DD date strings (inclusive).
        """
        # FIX(M21): use parameterised queries to prevent SQL injection
        query = f"""
        SELECT
          p.id   AS property_id,
          p.name AS property_name,
          p.urlSlug AS url_slug,
          r.type AS service_type,
          bn.date,
          COUNT(*) AS pet_days
        FROM {FQ}.booking_nights bn
        JOIN {FQ}.bookings b       ON bn.booking_id = b.id
        JOIN {FQ}.properties p     ON b.property_id = p.id
        JOIN {FQ}.booking_rooms br ON bn.booking_room_id = br.id
        JOIN {FQ}.rooms r          ON br.room_id = r.id
        WHERE bn.date >= @date_from
          AND bn.date <= @date_to
          AND b.status NOT IN ('cancelled', 'rejected')
          AND p.deleted_at IS NULL
        GROUP BY p.id, p.name, p.urlSlug, r.type, bn.date
        ORDER BY p.name, bn.date
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("date_from", "DATE", date_from),
                bigquery.ScalarQueryParameter("date_to", "DATE", date_to),
            ]
        )
        result = self.client.query(query, job_config=job_config).result()
        return [dict(row) for row in result]

    def get_revenue(self, date_from: str, date_to: str) -> list[dict]:
        """Daily revenue (AUD) by property and service type.

        ``booking_nights.price`` is stored in cents — divided by 100 here.
        """
        query = f"""
        SELECT
          p.id   AS property_id,
          p.name AS property_name,
          p.urlSlug AS url_slug,
          r.type AS service_type,
          bn.date,
          SUM(bn.price) / 100.0 AS revenue_aud
        FROM {FQ}.booking_nights bn
        JOIN {FQ}.bookings b       ON bn.booking_id = b.id
        JOIN {FQ}.properties p     ON b.property_id = p.id
        JOIN {FQ}.booking_rooms br ON bn.booking_room_id = br.id
        JOIN {FQ}.rooms r          ON br.room_id = r.id
        WHERE bn.date >= @date_from
          AND bn.date <= @date_to
          AND b.status NOT IN ('cancelled', 'rejected')
          AND p.deleted_at IS NULL
        GROUP BY p.id, p.name, p.urlSlug, r.type, bn.date
        ORDER BY p.name, bn.date
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("date_from", "DATE", date_from),
                bigquery.ScalarQueryParameter("date_to", "DATE", date_to),
            ]
        )
        result = self.client.query(query, job_config=job_config).result()
        return [dict(row) for row in result]

    def get_forward_bookings(
        self, as_at_date: str, weeks_forward: int = 12
    ) -> list[dict]:
        """Confirmed future bookings aggregated by property and ISO week.

        Used for forward visibility / working-capital forecasting.
        """
        query = f"""
        SELECT
          p.id   AS property_id,
          p.name AS property_name,
          r.type AS service_type,
          DATE_TRUNC(bn.date, WEEK(MONDAY)) AS week_start,
          COUNT(*) AS pet_days_booked,
          SUM(bn.price) / 100.0 AS revenue_booked
        FROM {FQ}.booking_nights bn
        JOIN {FQ}.bookings b       ON bn.booking_id = b.id
        JOIN {FQ}.properties p     ON b.property_id = p.id
        JOIN {FQ}.booking_rooms br ON bn.booking_room_id = br.id
        JOIN {FQ}.rooms r          ON br.room_id = r.id
        WHERE bn.date > @as_at_date
          AND bn.date <= DATE_ADD(@as_at_date, INTERVAL @weeks_forward WEEK)
          AND b.status IN ('confirmed', 'pending')
          AND p.deleted_at IS NULL
        GROUP BY p.id, p.name, r.type, week_start
        ORDER BY p.name, week_start
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("as_at_date", "DATE", as_at_date),
                bigquery.ScalarQueryParameter("weeks_forward", "INT64", weeks_forward),
            ]
        )
        result = self.client.query(query, job_config=job_config).result()
        return [dict(row) for row in result]
