
## Analise do protótipo do Adriano. 

- [x] Instalar/Configurar as dependencias nos containers
- [x] Organizar o diretórios de dados do serviço.
- [x] Alterar as funções para funcionar para uma unica coordenada. (O Exemplo do adriano está trabalhando com um np.Array como entrada para todas as funções, para o serviço é melhor que cada função trabalhe com apenas 1 input dessa forma é mais facil paralelizar as tarefas.)
- [X] Recuperar os tilenames e paths completos. (Código do adriano faz um find no diretório, a melhor opção é ter o path completo associado ao tilename.)
- [] Descompactar os Fits.fz em tempo de execução.
- [] Erro em cutouts com 3 tiles ({"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g", "format": "fits"},  # 3 - Tile)
- [] PNGs só tem opção de gerar imagens coloridas, usando gri. (Acredito que de para ter mais opções, png para uma banda só ou outras combinações.)

- [] CONFIRMAR se no metodo lupton sempre vai ser usado gri, a ordem é fixa? como fica para outros surveys.