"""
Schemas package — the API's TYPED CONTRACT (pydantic), separate from the DB.

Two different jobs, two different layers, easy to confuse:
    models/   SQLAlchemy — how data is STORED (tables, constraints)
    schemas/  pydantic   — how data crosses the HTTP WIRE (requests/responses)

Keeping them apart means the public shape of the API doesn't leak internal
columns by accident, and either can change without dragging the other.
"""
