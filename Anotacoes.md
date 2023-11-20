
## Analise do protótipo do Adriano. 

- [x] Instalar/Configurar as dependencias nos containers
- [x] Organizar o diretórios de dados do serviço.
- [x] Alterar as funções para funcionar para uma unica coordenada. (O Exemplo do adriano está trabalhando com um np.Array como entrada para todas as funções, para o serviço é melhor que cada função trabalhe com apenas 1 input dessa forma é mais facil paralelizar as tarefas.)
- [] Recuperar os tilenames e paths completos. (Código do adriano faz um find no diretório, a melhor opção é ter o path completo associado ao tilename.)
- [] Descompactar os Fits.fz em tempo de execução.
- [] PNGs só tem opção de gerar imagens coloridas, usando gri. (Acredito que de para ter mais opções, png para uma banda só ou outras combinações.)
