"""Database connectivity and, later, the PostGIS repository implementation.

The only package permitted to construct a SQLAlchemy `Engine` (`db-005`), and
the only one that will import PostGIS types (`db-001`, `db-003`). Everything
above it -- the DAL, the adapters, the route handlers -- talks to the
repository port in `app.dal.repository` and knows nothing about the storage
engine behind it.
"""
