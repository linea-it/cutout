

# Cutout Service

Microserviço com o objetivo de dar aos usuários acesso a recortes de imagens dos surveys mantidos pelo LIneA. 

Cutout geramente são imagens pequenas de uma area do ceu, podendo ser em formato de dados (Fits) ou Imagem (Png).



## Sobre os formatos de imagens

   **Fits**: é um formato de dados que permite processamento/analise. As imagens tem diferentes bandas que podem ser combinadas. Arquivos com tamanho consideravel, é necessário carregar o arquivo todo na memória para manipulalo. Não é possivel visualizar no brownser.

   **Png**: formato de imagem convencional, gerado a partir de 3 ou mais fits em bandas diferentes no caso de cutouts coloridos. Não permite Analise mas pode ser processado como redimensionamento, adicionar texto ou legendas. Possivel visualizar no brownser.

## Casos de Usos. 

*Usuário* pode ser um individuo, um script ou uma aplicação interna do LIneA.

### Real Time Job

Usuario quer gerar um cutout para uma coordenada especifica.

- Faz uma requisição com suas credencias para a API passando como parametro survey, RA, Dec, Size, Formato (Fits, Png), algoritimo, banda.
- Cutout Service autentica o usuario, registra a solicitação, valida os parametros, checa se é possivel atender o pedido em tempo habil (calculo de tempo baseado no tamanho do cutout ou outros fatores utilizando o histórico de execuções.)
- Em caso positivo, processa e retorna o cutout como resultado da requisição. 
- Caso a requisição não atenda os critérios de real time ou tenha alguma inconsistencia nos parametros retorna mensagem clara explicando o problema e sugestão de solução se possivel.
- Cutout Service, atualiza o registro da solicitação com status, tempo, tamanho, etc.
- Usuario no retorno da requisição, pode estar salvando o resultado como arquivo (download) ou pode estar exibindo a imagem direto no jupyter notebook ou navegador.

### Async Time Job
    
Usuario quer gerar varios cutouts pode ser para uma mesma coordenada (bandas diferentes, formatos diferentes, tamanhos, algoritimos, surveys?) 1 coordenada para N cutouts. Ou uma lista de coordenadas e diferentes parametros, N coordenadas para N Cutouts.

- Faz uma requisição com suas credencias para a API passando dois conjuntos de parametros para um referente a geração das imagem ( survey, RA, Dec, Size, Formato (Fits, Png), algoritimo, banda.) e outro a lista/array de coordenadas (RA e DEC ou ID, RA e DEC sendo o id forncedico pelo usuario que serve para associar as imagens as coordenadas)
- Cutout Service autentica o usuario, registra a solicitação, valida os parametros, faz a estimativa de tempo considerando a posição na fila e prioridades Inclui o job na fila e retorna ao usuario o id do job e as estimativas, ou mensagem de erro/validação.
- Usuario com o id do job vai consultar a API para saber o status/andamento do job. Em algum momento o status vai ser concluido e nesta resposta deve ter as informações necessárias para o usuario fazer o download dos resultados e um summary da execução do job.
- O download dos resultados pode ser um unico arquivo compactado (dependendo do tamanho) ou download individual de cada cutout. 
* O resultado pode ser disponibilizado via Download ou em um diretório da estrutura do LIneA (Home do usuario por exemplo para acesso pelo Jupyter Notebook ou outro diretório no caso das aplicações.)


## Requisitos

- Real Time Job - Permitir a geração de cutouts a partir de uma requisição simples, se possivel o retorno da requisição já sendo o cutout. ( Job deve ser limitado a um tempo de execução curto)

- Async Job - Permitir a geração de cutouts em lotes, a API recebe uma lista de coordenadas e parametros, um job é criado e adicionado a fila. ( Job deve ser limitado em volume de armazenamento e ou quantidade de coordenadas.)

- Suporte a mais de um Survey ( uma implementação com uma camada na frente dos códigos que efetivamente cortam a imagem.)
- Suporte a 2 formatos de imagens Fits e Png
- Suporte a 2 algoritimos. 
- Permitir cutout de objetos na borda.
- Paralelismo na geração de imagens.
- Gestão de Jobs/Fila para processos longos.
- Real Time Job devem ter prioridade.
- Usuário deve ter acesso a fila de jobs
- Usuário deve ter algum nivel de gestão dos seus jobs (visualizar os jobs submetidos, cancelar, acompanhar status, ver jobs completos, remover ). 
- Gestão dos resultados gerados, deve ficar disponivel por um periodo ex: 1 semana e ser apagado automaticamente depois do periódo (Garbage Colector).
- Autenticação dos usuários CILogon, LDAP
- Autenticação entre os serviços internos do linea, mas deve ser possivel identificar o usuario. 
- Algum controle de permissão, saber se o usuario tem acesso ao survey que está sendo solicitado.
- Armazenar os tempos de execução/resposta as solicitações e permitir calculo de estimativa de execução.
- Fornecer estimativas de tempo de execução e volume de armazenamento ao incluir um novo job.
- O Cutout deve ter uma ligação forte com a coordenada. deve ser possivel identificar exatamente  quais arquivos foram gerados para cada coordenada de preferencia que esta informação seja acessivel de forma programatica (um json ou csv no diretório dos resultados ou algum endpoint).
- Ter algum sistema de prioridade. ex: por usuario prioritário, usuarios internos ou sistema interno.
- Testar qual o area (graus) maximo de cutout, talvez implementar a produção da imagem em varios pedaços pequenos, junta-los. nas pngs talvez fazer um downscale para um tamanho amigavel ( pixels ).
- Algum sistema de Cotas (quantidade de cutouts, armazenamento ou tempo) por usuario ou grupos.
- Alguma interface Administrativa para debug/monitoramento.
- Job deve ter alguma tolerancia a falha, exemplo falhar alguns cutouts e continuar o job, ou o job falha mas permitir recomeçar aproveitando os cutouts já gerados.
- Separar o processamento entre cutouts que envolvem uma unica imagem, dos cutouts que estão na borda que envolve mais de uma imagem nestes casos é possivel ter problemas com a quantidade de memoria necessária, dependendo da implementação e local onde o job é executado.
- Notificação por email nos Async Jobs

## Tecnologias

- Prefencia para Python 3.9 ou acima.
- framework Django preferencialmente ou Flask.
- Enviroment em container.
- Paralelismo 2 opções a serem testadas e avaliadas: 
    - Celery + Rabbitmq  Mais amigavel com aplicações web compatibilidade com as outras aplicações. podendo compartilhar um mesmo servidor Rabbitmq (que ainda não foi implementado mas desejo no futuro proximo), facil implementação, escalavel, menor performance.
    - Parsl + HTCondor Nada amigavel com aplicações web, alta dependencia do ambiente, alta complexidade, pouca estabilidade. Muita performance.
