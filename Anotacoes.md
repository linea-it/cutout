# Anotações Cutout Service

## Serviço/Infra

- [x] Documentação do Endpoint usando OpenApi schema.
- [X] Tratar valores do Parametro POS xtype Circle, Range e  Polygon.
- [x] Instalar/Configurar as dependencias nos containers
- [x] Organizar o diretórios de dados do serviço.
- [x] Classe Base para Cutots de forma que outros surveys possam ser adicioandos.
- [] Filenames Unicos para os resultados ???
- [] SODA parametro band está em numerico, usamos letras e isso é importante no caso do des por causa dos arquivos. procurar um parametro alternativo para representar as bandas com letras.
- [] Quanto tempo os arquivos gerados por um job ficam disponiveis para download, antes do garbage collector remover.
- [] CONFIRMAR se no metodo lupton sempre vai ser usado como gri, a ordem é fixa? como fica para outros surveys.
- [] Quanto tempo os arquivos fits extraidos ficam disponiveis.
- [] Como lidar como essa parte do protocolo: 3.2.1 As in DALI, open intervals use  -Inf or +Inf as one limit.
- [] Implementar respostas de erro no formado esperado pelo SODA.
- [] Como gerar o token de autenticação usando a autenticação Federada SAML?
- [] Cutouts anonimos?
- [] Configurar Ngnix no projeto
- [] Criar uma rota para cada serviço
- [] Remover o prefixo /api dos endpoits acessar direto ex: cutout.linea.org.br/sync
- [] Documentação da Classe Cutout Base
- [] Documentação da Classe DES Cutout
- [] Garbage Collector para arquivos fits de imagens descompactados.
- [] Garbage Collector para resultados.
- [] Sistema de Quota por espaço

## Cutout Sync DES

- [x] Alterar as funções para funcionar para uma unica coordenada. (O Exemplo do adriano está trabalhando com um np.Array como entrada para todas as funções, para o serviço é melhor que cada função trabalhe com apenas 1 input dessa forma é mais facil paralelizar as tarefas.)
- [x] Recuperar os tilenames e paths completos. (Código do adriano faz um find no diretório, a melhor opção é ter o path completo associado ao tilename.)
- [x] Descompactar os Fits.fz em tempo de execução.
- [X] Endpoint Sync para cutouts DES POS Circle Fits.
- [X] Cutout Sync em background com Celery.
- [] Endpoint Sync para cutouts DES POS Circle Png.
- [] Endpoint Sync para cutouts DES POS Polygon Jpg.
- [] função para Cutout DES usando Range de posições.
- [] função para Cutout DES usando Poligono.
- [] Registrar a criação do cutout sync na listas de job do usuario???
- [] PNGs só tem opção de gerar imagens coloridas, usando gri. (Acredito que de para ter mais opções, png para uma banda só ou outras combinações.)
- [] Criar exemplos de uso da api no Jupyter Notebook.

## Cutout Sync LSST

- [] Quais as bandas usadas no LSST, o parametro band do endpoint acredito que deva ser livre e o valor deve ser tratado de acordo com o release.
- [] Implementar classe LSST Cutout
- [] Configurar acesso as imagens do LSST.
- [] Descompactar em tempo de execuçõa???

## Cutout Async DES

- [] Submeter lista de coordenadas para processamento em background com celery.
- [] Email com informação do job asyncrono. (opcional)
- [] Definir Limit qtd/tamanho de Cutouts

## Monitoramento dos Jobs

- [] Regitrar no banco de dados cada cutout criado pelo usuario. (Incluir Cutouts Sync?)
- [] Interface com a lista de Jobs
- [] Download dos resultados do job.
- [] Cancelar/Deletar um Job.
- [] Mostrar uso da quota?
- [] Limite de Jobs?

## Deploy dev

- [] URL/Porta expecifica para o serviço
- Pipeline github actions para build das imagens docker.
  - [] Build do container do serviço.
  - [] Build da documentação.
