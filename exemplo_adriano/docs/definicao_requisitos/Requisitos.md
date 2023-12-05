

# Cutout Service

Microserviço com o objetivo de dar aos usuários acesso a recortes de imagens dos surveys mantidos pelo LIneA.

Cutout geramente são imagens pequenas de uma area do ceu, podendo o arquivo final ser em formato Fits, Jpg ou Png.



## Sobre os formatos de imagens

   **Fits**: é um formato de dados convencional em Astronomia que permite mais fácil acesso aos dados, sendo que geralmente se refere aos dados de uma única banda. Arquivos com tamanho consideravel, é necessário carregar o arquivo todo na memória para a manipulação. Não é possivel visualizar no browser, sendo geralmente usado um software como o SAODS9 para visualização.

   **Png** ou **Jpg**: formato de imagem convencional para visualização, sendo geralmente a combinação RGB de 3 ou mais fits em bandas diferentes no caso de cutouts coloridos. Não permite análise mas pode ser processado como redimensionamento, adicionar texto ou legendas. Passivel de visualização no browser.

## Casos de Usos.

*Usuário* pode ser um individuo, um script ou uma aplicação interna do LIneA.

Geralmente o usuário solicita imagens para visualização, tratamento ou outra análise no caso de confirmação visual de um possível objeto.

### Real Time Job

Usuario quer gerar um cutout para uma coordenada específica.

- Faz uma requisição com suas credencias para a API passando como parametro survey, RA, Dec, Size, Formato (Fits, Png), algoritmo para combinação de cores, banda.
- Cutout Service autentica o usuario, registra a solicitação, valida os parametros, checa se é possivel atender o pedido em tempo hábil (cálculo de tempo baseado no tamanho do cutout ou outros fatores utilizando o histórico de execuções).
- Em caso positivo, processa e retorna o cutout como resultado da requisição.
- Caso a requisição não atenda os critérios de real time ou tenha alguma inconsistência nos parâmetros retorna mensagem clara explicando o problema e sugestão de solução, se possivel.
- Cutout Service atualiza o registro da solicitação com status, tempo, tamanho, etc.
- Usuário no retorno da requisição, pode estar salvando o resultado como arquivo (download) ou pode estar exibindo a imagem direto no jupyter notebook ou navegador.

### Async Time Job

No caso do usuário querer gerar varios cutouts para uma mesma coordenada (bandas diferentes, formatos diferentes, tamanhos, algoritimos, ou surveys) ou uma mesma coordenada para vários cutouts. Ou ainda uma lista de coordenadas e diferentes parametros.

- Faz uma requisição com suas credencias para a API passando dois conjuntos de parametros referente a geração das imagens (survey, RA, Dec, Size, Formato (Fits, Png), algoritmo, banda) e outro parâmetro como a lista de coordenadas (RA e DEC ou ID, RA e DEC sendo o id forncedico pelo usuário que serve para associar as imagens às coordenadas);
- Cutout Service autentica o usuário, registra a solicitação, valida os parâmetros, faz a estimativa de tempo considerando a posição na fila e prioridades. Inclui o job na fila e retorna ao usuário o id do job e as estimativas, ou mensagem de erro/validação.
- Usuário com o id do job vai consultar a API para saber o status/andamento do job. Em algum momento o status vai ser concluído e esta resposta deve conter as informações necessárias para o usuário fazer o download dos resultados juntamente com um summary da execução do job.
- O download dos resultados pode ser um único arquivo compactado (dependendo do tamanho) ou download individual de cada cutout.
* O resultado pode ser disponibilizado via Download ou em um diretório da estrutura do LIneA (home do usuario por exemplo para acesso pelo Jupyter Notebook ou outro diretório no caso das aplicações).


## Requisitos

- Real Time Job - permitir a geração de cutouts a partir de uma requisição simples, se possível o retorno da requisição já sendo o cutout (job deve ser limitado a um tempo de execução curto).

- Async Job - permitir a geração de cutouts em lotes, a API recebe uma lista de coordenadas e parâmetros, um job é criado e adicionado a fila (job deve ser limitado em volume de armazenamento e ou quantidade de coordenadas).

- Suporte a mais de um survey (uma implementação com uma camada na frente dos códigos que efetivamente cortam a imagem);
- Suporte a 2 formatos de imagens Fits e Png;
- Suporte a 2 algoritimos;
- Permitir cutout de objetos na borda;
- Paralelismo na geração de imagens;
- Gestão de Jobs/Fila para processos longos;
- Real Time Job devem ter prioridade;
- Usuário deve ter acesso a fila de jobs;
- Usuário deve ter algum nivel de gestão dos seus jobs (visualizar os jobs submetidos, cancelar, acompanhar status, ver jobs completos, remover);
- Gestão dos resultados gerados: o arquivo deve ficar disponivel por um certo período de tempo e ser apagado automaticamente depois do perído (Garbage Colector).
- Autenticação dos usuários CILogon, LDAP;
- Autenticação entre os serviços internos do LIneA, mas deve ser possivel identificar o usuário;
- Algum controle de permissão para saber se o usuário tem acesso ao survey que está sendo solicitado;
- Armazenar os tempos de execução/resposta às solicitações e permitir cálculo de estimativa de execução;
- Fornecer estimativas de tempo de execução e volume de armazenamento ao incluir um novo job;
- O Cutout deve ter uma ligação forte com a coordenada. Deve ser possivel identificar exatamente quais arquivos foram gerados para cada coordenada de preferência que esta informação seja acessível de forma programática (um json ou csv no diretório dos resultados ou algum endpoint);
- Ter algum sistema de prioridade ou filas. Ex.: usuário prioritário, usuários internos ou sistema interno;
- Testar qual a área (em graus quadrados) máximo do cutout, talvez implementar a produção da imagem em varios pedaços pequenos e então juntá-los. Nas pngs talvez fazer um downscale para um tamanho amigavel, reescalonando em pixels;
- Algum sistema de Cotas (quantidade de cutouts, armazenamento ou tempo) por usuário ou grupos;
- Alguma interface Administrativa para debug/monitoramento;
- Job deve ter alguma tolerância a falhas. Por exemplo falhar alguns cutouts e continuar o job, ou o job falhar mas permitir recomeçar aproveitando os cutouts já gerados;
- Separar o processamento entre cutouts que envolvem uma única imagem dos cutouts que estão na borda e que envolve mais de uma imagem. Nestes casos é possivel ter problemas com a quantidade de memoria necessária, dependendo da implementação e local onde o job é executado;
- Notificação por email nos Async Jobs;
- Legendas nos cutouts png (sobre a imagem ou em uma borda).

## Tecnologias

- Preferência para Python 3.9 ou acima.
- Framework Django preferencialmente ou Flask.
- Enviroment em container.
- Paralelismo 2 opções a serem testadas e avaliadas:
    - Celery + Rabbitmq: Mais amigável com aplicações web compatíveis com as outras aplicações. Pode ser compartilhado em um mesmo servidor Rabbitmq (que ainda não foi implementado mas é desejável num futuro próximo), fácil implementação, escalável e melhor performance.
    - Parsl + HTCondor Nada amigavel com aplicações web, alta dependencia do ambiente, alta complexidade, pouca estabilidade. Muita performance.
