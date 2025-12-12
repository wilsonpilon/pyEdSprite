# pyEdSprite

Editor de sprites **MSX1** (estilo **TMS9918A**) feito em **Python** com interface gráfica, pensado como um MVP simples e direto: desenhe sprites **8x8** ou **16x16**, escolha a cor (1 cor por sprite, como no MSX1), visualize miniaturas em grade e salve tudo em **SQLite**.

---

## Ideia do projeto

O MSX1 trabalha com sprites com limitações bem específicas (tamanho fixo, **1 cor por sprite**, paleta reduzida, e composição de sprites maiores por blocos). Este projeto nasceu para facilitar:

- criar e editar sprites rapidamente;
- montar sprites maiores a partir de blocos (2x2);
- simular composição por “camadas” (overlay);
- manter projetos salvos localmente sem complicação (SQLite).

---

## Funcionalidades

- **Tamanhos de sprite:** `8x8` e `16x16`
- **Paleta MSX1 (16 cores):** seleção por índice `0..15`
  - Observação: o índice `0` costuma ser “transparente” em MSX; aqui é exibido como preto para visualização.
- **Grade de sprites com miniaturas** (seleção por clique)
- **Editor com grid** (clique para ligar/desligar pixels)
  - Botão esquerdo: desenha (pixel ligado)
  - Botão direito: apaga (pixel desligado)
- **Preview 2x** do sprite (ou composição, conforme modo)
- **Salvar projeto em SQLite** (`sprites.db`)

---

## Modos de operação

### 1) `single`
Edita **um sprite por vez** (o selecionado na grade).

### 2) `2x2`
Edita um bloco **2x2** de sprites adjacentes como se fosse um sprite maior:
- Para sprites `8x8`: edita uma área total `16x16` (2x2 sprites 8x8)
- Para sprites `16x16`: edita uma área total `32x32` (2x2 sprites 16x16)

> Dica: nas bordas da grade pode não existir um bloco 2x2 válido; selecione um sprite “mais para dentro” da grade.

### 3) `overlay`
Empilha visualmente 4 sprites (bloco 2x2) na mesma área **(mesmo tamanho do sprite)**:
- O preview mostra a composição das 4 “camadas”
- Você escolhe qual camada editar (1 a 4) no seletor “Overlay: editar sprite”

---

## Como os dados são organizados

- O projeto mantém uma lista de sprites em memória.
- Cada sprite guarda:
  - `size` (8 ou 16)
  - `color_index` (0..15)
  - `rows` (máscaras de bits por linha)
- Ao salvar:
  - Cria/atualiza um registro do projeto
  - Armazena cada sprite como **BLOB** no SQLite
    - `8x8`: 8 bytes (1 byte por linha)
    - `16x16`: 32 bytes (2 bytes por linha)

---

## Requisitos

- **Python 3.14+** (o projeto foi pensado para rodar com Python moderno)
- Biblioteca padrão:
  - `tkinter` (GUI)
  - `sqlite3` (persistência)
- Dependência externa:
  - `customtkinter`

---

## Instalação

Com o ambiente virtual já configurado (recomendado):
