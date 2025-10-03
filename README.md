# Sistema de Postagens dos Correios

Sistema web completo para gerenciar dois postos de postagem dos Correios, desenvolvido em Python com Flask.

## 🚀 Funcionalidades

### ✅ **Registro de Postagens**
- Formulário intuitivo para inserir dados de envio
- Campos: nome do remetente, código de rastreio, valor, tipo (PAC/SEDEX), pagamento (PIX/DINHEIRO)
- Validação automática dos dados
- Controle por posto (Posto 1 ou Posto 2)

### ✅ **Dashboard Completo**
- Resumo em tempo real dos dois postos
- Estatísticas por tipo de postagem e forma de pagamento
- Lista de todas as postagens do dia
- Interface visual moderna e responsiva

### ✅ **Fechamento Diário**
- Geração automática de resumos por posto
- Registro do funcionário responsável
- Observações personalizadas
- Prevenção de fechamentos duplicados

### ✅ **Banco de Dados**
- SQLite integrado (sem necessidade de servidor)
- Tabelas otimizadas para postagens e fechamentos
- Integridade referencial garantida

## 📋 **Pré-requisitos**

- Python 3.7 ou superior
- pip (gerenciador de pacotes Python)

## 🔧 **Instalação e Execução**

### 1. **Clone ou baixe os arquivos**
Certifique-se de ter todos os arquivos em uma pasta:
```
sistema-postagens/
├── app.py
├── postagens.db
├── requirements.txt
├── README.md
└── templates/
    ├── base.html
    ├── index.html
    ├── nova_postagem.html
    └── fechamento.html
```

### 2. **Instale as dependências**
```bash
pip install flask
```
ou
```bash
pip install -r requirements.txt
```

### 3. **Execute o sistema**
```bash
python app.py
```

### 4. **Acesse o sistema**
Abra seu navegador e vá para:
```
http://localhost:5000
```

## 📱 **Como Usar**

### **Nova Postagem**
1. Clique em "Nova Postagem"
2. Preencha todos os campos obrigatórios:
   - **Data**: Data da postagem
   - **Posto**: Escolha entre Posto 1 ou Posto 2
   - **Nome do Remetente**: Nome completo
   - **Código de Rastreio**: 13 caracteres (ex: AA123456789BR)
   - **Valor**: Valor da postagem em reais
   - **Tipo**: PAC ou SEDEX
   - **Pagamento**: PIX ou Dinheiro
3. Clique em "Registrar Postagem"

### **Dashboard**
- Visualize resumos automáticos dos dois postos
- Acompanhe o total de postagens e valores do dia
- Veja estatísticas por tipo de serviço e forma de pagamento
- Liste todas as postagens registradas

### **Fechamento do Dia**
1. Acesse "Fechamento do Dia"
2. Revise os resumos de cada posto
3. Clique em "Realizar Fechamento" do posto desejado
4. Informe o nome do funcionário responsável
5. Adicione observações se necessário
6. Confirme o fechamento

## 🛡️ **Validações Automáticas**

- **Código de rastreio único**: Não permite duplicatas
- **Valores positivos**: Valores devem ser maiores que zero
- **Campos obrigatórios**: Todos os campos essenciais são validados
- **Formato de dados**: Datas, números e texto são validados

## 🎨 **Interface**

- **Design moderno**: Interface limpa com Bootstrap 5
- **Responsiva**: Funciona em desktop, tablet e celular
- **Cores diferenciadas**: Posto 1 (azul) e Posto 2 (verde)
- **Ícones intuitivos**: Cada função tem ícones representativos
- **Alertas visuais**: Mensagens de sucesso e erro claras

## 🗃️ **Estrutura do Banco**

### **Tabela: postagens**
- `id`: Identificador único
- `data_postagem`: Data da postagem
- `posto`: Número do posto (1 ou 2)
- `nome_remetente`: Nome do remetente
- `codigo_rastreio`: Código único de rastreamento
- `valor`: Valor da postagem
- `tipo_postagem`: PAC ou SEDEX
- `tipo_pagamento`: PIX ou DINHEIRO
- `status`: Status da postagem
- `data_criacao`: Timestamp de criação

### **Tabela: fechamento_diario**
- `id`: Identificador único
- `data_fechamento`: Data do fechamento
- `posto`: Número do posto
- `total_postagens`: Quantidade de postagens
- `total_valor`: Valor total
- `total_pac`: Quantidade PAC
- `total_sedex`: Quantidade SEDEX
- `total_pix`: Valor total PIX
- `total_dinheiro`: Valor total dinheiro
- `funcionario`: Nome do responsável
- `observacoes`: Observações do fechamento

## 🚨 **Resolução de Problemas**

### **Erro "Module not found"**
```bash
pip install flask
```

### **Banco não encontrado**
O arquivo `postagens.db` é criado automaticamente na primeira execução.

### **Porta em uso**
Altere a porta no arquivo `app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Mude para 5001
```

### **Problemas de permissão**
Execute como administrador ou verifique permissões da pasta.

## 📊 **Recursos Avançados**

- **API REST**: Endpoint `/api/resumo/<data>/<posto>` para integrações
- **Backup automático**: Banco SQLite permite backup simples
- **Expansível**: Código preparado para novas funcionalidades
- **Multiplataforma**: Funciona em Windows, Mac e Linux

## 🔮 **Próximas Versões**

- [ ] Relatórios mensais
- [ ] Exportação para Excel
- [ ] Integração com API dos Correios
- [ ] Sistema de usuários
- [ ] Dashboard analítico

---

**Desenvolvido por RobTech Service**  
Sistema completo para gestão de postos de postagem dos Correios  
Contato: robtechservice@outlook.com
