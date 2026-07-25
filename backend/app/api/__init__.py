# API package — HTTP routers. Each module owns one resource area and stays
# THIN: parse the request, call a service, shape the response, map errors to
# status codes. No business logic here — that lives in services/.
