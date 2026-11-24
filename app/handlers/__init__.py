from app.handlers import admin, ai, cart, catalog, search, start

# Tartib muhim: yuqoridagi router birinchi tekshiriladi
routers = [start.router, admin.router, catalog.router, cart.router, search.router, ai.router]
