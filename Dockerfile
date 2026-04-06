# Dockerfile pour HuggingFace Spaces
# HF Spaces exige : port 7860 + utilisateur UID 1000

FROM python:3.11-slim

# Créer un utilisateur non-root (requis par HuggingFace Spaces)
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Installer les dépendances Python
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY --chown=user . .

# HuggingFace Spaces utilise le port 7860
EXPOSE 7860

# Lancer Chainlit sur le bon port
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "7860"]
