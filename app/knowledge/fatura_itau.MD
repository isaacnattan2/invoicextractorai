# Knowledge Base – Fatura de Cartão de Crédito Itaú (Brasil)

Este documento descreve regras, padrões e exclusões para extração correta de despesas
em faturas de cartão de crédito do Itaú.

Seu objetivo é ajudar o LLM a:
- Extrair somente compras reais
- Evitar duplicações
- Ignorar pagamentos, juros e textos explicativos

---

## 1. O QUE É UMA TRANSAÇÃO VÁLIDA

Uma transação válida representa uma **compra ou saque** feito no cartão.

Uma transação válida **SEMPRE** possui:
- Uma data no formato DD/MM
- Um nome de estabelecimento comercial
- Um valor positivo
- Está localizada na seção:
  **"Lançamentos: compras e saques"**

Exemplo válido:
28/11 IFD*60463747CAMILLYLA 53,98

yaml
Copiar código

---

## 2. O QUE NÃO DEVE SER EXTRAÍDO (REGRA CRÍTICA)

⚠️ **NUNCA extraia como despesa**:

### Pagamentos e créditos
- PAGAMENTOPIX
- Pagamento efetuado
- Total dos pagamentos
- Crédito
- Estorno

Exemplo inválido:
07/11 PAGAMENTOPIX -150,19

yaml
Copiar código

---

### Juros, encargos e informações financeiras
- Juros do rotativo
- Juros de mora
- Multa por atraso
- IOF
- CET
- Encargos financeiros
- Crédito rotativo

---

### Textos explicativos que causam duplicação
⚠️ Estes textos **NÃO representam compras**, mesmo que apareçam próximos a valores:

- Novo teto de juros do cartão de crédito
- Limite máximo de juros
- Juros e encargos financeiros até o momento
- % sobre o limite máximo de juros
- Simulação de compras parceladas
- Limites de crédito
- Limite disponível
- Limite total utilizado

❌ Estes textos costumam gerar **duplicatas falsas** e devem ser ignorados.

---

## 3. DELIMITAÇÃO DE CONTEXTO (MUITO IMPORTANTE)

Apenas o conteúdo **ENTRE** os marcadores abaixo pode conter transações:

### Início válido
Lançamentos: compras e saques

shell
Copiar código

### Fim válido
Lançamentos no cartão

nginx
Copiar código
ou
Total dos lançamentos atuais

yaml
Copiar código

👉 Qualquer texto fora desse intervalo **não contém despesas**.

---

## 4. PADRÃO REAL DAS COMPRAS

Formato típico:
DD/MM NOME_DO_ESTABELECIMENTO VALOR

java
Copiar código

Pode haver texto adicional abaixo (cidade / categoria), que deve ser ignorado.

Exemplo:
26/11 IFD*VSSERVICOSDEALIA 122,88
restaurante city

yaml
Copiar código

✅ Apenas a primeira linha representa a transação.

---

## 5. DEDUPLICAÇÃO (REGRA OBRIGATÓRIA)

Considere duas transações duplicadas se tiverem:
- Mesma data
- Mesmo estabelecimento (normalizado)
- Mesmo valor

⚠️ Mesmo que apareçam em contextos diferentes do texto.

---

## 6. EXEMPLOS POSITIVOS

```json
{
  "date": "2025-11-26",
  "description": "IFD*VSSERVICOSDEALIA",
  "amount": 122.88,
  "installment": null,
  "currency": "BRL"
}
7. EXEMPLOS NEGATIVOS (NÃO EXTRAIR)
text
Copiar código
Novo teto de juros do cartão de crédito
Limite máximo de juros 0,00
P Total dos pagamentos -150,19
8. OBJETIVO FINAL DO MODELO
Extrair somente compras reais, com alta precisão, evitando:

Pagamentos

Repetições

Reinterpretação de textos financeiros

Se houver dúvida, prefira não extrair.