
## Analise do protótipo do Adriano. 

- [x] Instalar/Configurar as dependencias nos containers
- [x] Organizar o diretórios de dados do serviço.
- [x] Alterar as funções para funcionar para uma unica coordenada. (O Exemplo do adriano está trabalhando com um np.Array como entrada para todas as funções, para o serviço é melhor que cada função trabalhe com apenas 1 input dessa forma é mais facil paralelizar as tarefas.)
- [X] Recuperar os tilenames e paths completos. (Código do adriano faz um find no diretório, a melhor opção é ter o path completo associado ao tilename.)
- [X] Descompactar os Fits.fz em tempo de execução.
- [] Erro em cutouts com 3 tiles ({"ra": 35.23676, "dec": -10.33269, "size": 10.0, "band": "g", "format": "fits"},  # 3 - Tile)
- [] PNGs só tem opção de gerar imagens coloridas, usando gri. (Acredito que de para ter mais opções, png para uma banda só ou outras combinações.)

- [] CONFIRMAR se no metodo lupton sempre vai ser usado gri, a ordem é fixa? como fica para outros surveys.
- [] SODA parametro band está em numerico, usamos letras e isso é importante no caso do des por causa dos arquivos. procurar um parametro alternativo para representar as bandas com letras.
- [X] Tratar valores do Parametro POS xtype Circle, Range e  Polygon.
- [] função para Cutout usando Range de posições.
- [] função para Cutout usando Poligono.
- [] Quanto tempo os arquivos gerados por um job ficam disponiveis para download, antes do garbage collector remover.
- [] Quanto tempo os arquivos fits extraidos ficam disponiveis.
- [] Quais as bandas usadas no LSST, o parametro band do endpoint acredito que deva ser livre e o valor deve ser tratado de acordo com o release.
- [] Como lidar como essa parte do protocolo: 3.2.1 As in DALI, open intervals use  -Inf or +Inf as one limit.
- [] Implementar respostas de erro no formado esperado pelo SODA.