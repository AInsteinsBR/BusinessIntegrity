# Bussiness Integrity

## Configuração do Ambiente

### **1. Pré-requisitos**
- Python 3.12 ou superior.
- Ambiente virtual configurado com `venv`.

### **2. Instalação**
1. Clone o repositório:
   ```bash
   git clone https://github.com/AInsteinsBR/BusinessIntegrity.git
   cd BusinessIntegrity
   ```

2. Crie e ative o ambiente virtual:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Para Linux/Mac
   venv\Scripts\activate  # Para Windows
   ```

3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure o as variáveis de ambiente
   - Substitua o arquivo `.env-example` por `.env` e preencha as variáveis necessárias.
   - Neste projeto foi utilizado os modelos da Cohere hospeados pela plataforma [cohere](https://cohere.com/).
        - Crie uma conta no site e obtenha a chave `COHERE_API_KEY`.
   - Para usar o OpenAI, configure a chave `OPENAI_API_KEY`.
        - Para obter a chave, acesse: [openai.com](https://openai.com/)
   - Para buscar nas páginas do Google, configure a chave `SERPER_API_KEY`.
        - Para obter a chave, acesse: [serper.dev](https://serper.dev/)
   - Passe as informações do seu banco de dados MySQL para o arquivo `.env`
   - Exporte as variáveis de ambiente:
        ```bash
        export COHERE_API_KEY=...
        export OPENAI_API_KEY=...
        export SERPER_API_KEY=...
        export DB_HOST=...
        export DB_USER=...
        export DB_PASSWORD=...
        export DB_NAME=...
        ```

5. Para criar as tabelas no banco de dados, execute:
    ```bash
    python3 config.py
    ```

5. Execute a aplicação de demonstração:
   ```bash
   EXPORT FLASK_APP=app/app.py
   flask run
   ```