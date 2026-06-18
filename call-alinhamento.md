Attendees: AUTO VIP, Raul Behnke
Visão Geral

A reunião teve como objetivo alinhar e mapear o processo comercial e os requisitos técnicos para a implantação do novo sistema de CRM, com foco na migração de dados, automação de follow-ups e integração de inteligência artificial. Foram apresentadas as três fases da implementação — migração, desenvolvimento das automações e integração da IA —, definindo estratégias para centralizar a comunicação via WhatsApp e otimizar o atendimento comercial.

Principais Conclusões

Iniciou-se a implantação seguindo três fases bem definidas, com previsão de dois meses para execução.
Optou-se por utilizar a API externa do WhatsApp para testes, com medidas preventivas para evitar banimentos.
Concluiu-se pela concessão de acesso administrativo ao Chat Guru para a extração e migração dos dados existentes.
Ficou acordado o agendamento de treinamento com a equipe, com envio de calendário em até uma semana.

Próximos Passos

Michael: Fornecer acesso administrativo ao Chat Guru para que Raul possa extrair os dados já existentes.
Raul Behnke: Enviar o calendário e agendar o treinamento com a equipe para iniciar a integração e migração do CRM.
Raul Behnke: Monitorar a performance da API externa do WhatsApp e ajustar a integração, se necessário.
Raul Behnke: Iniciar a migração dos dados para a implementação da nova solução de CRM.
Principais Tópicos
Metodologia de Implantação e Fases do Projeto Decisão
Raul apresentou a metodologia dividida em três fases: Migração (coleta de dados e treinamento, com duração de aproximadamente 1 semana), Desenvolvimento das Automações (com duração de 3 semanas) e Integração da IA (com duração de 1 mês), totalizando 2 meses.
Hugo foi mencionado como o responsável técnico pela implementação.
O foco está em mapear o fluxo comercial atual para automatizar processos como follow-ups e atendimento, integrando as automações e a IA.
Integração e Migração dos Dados do CRM Atual Decisão
Foi discutida a necessidade de migrar os dados já existentes do Chat Guru para a nova plataforma, evitando iniciar a operação do zero.
Raul solicitou acesso administrativo ao Chat Guru para poder extrair e integrar informações como histórico de negociações e leads.
A integração fará com que os dados atuais sejam centralizados e aproveitados na nova solução.
Configuração e Automação do Atendimento via WhatsApp Decisão
A reunião destacou que a operação utiliza um único WhatsApp oficial para todos os colaboradores, que têm suas mensagens gerenciadas centralizadamente.
Foi decidido iniciar utilizando a API externa do WhatsApp para testar o funcionamento, com possibilidade de migração para a API oficial caso ocorram problemas como banimento.
Medidas foram discutidas para mitigar riscos relacionados à qualidade de entrega e ao banimento, com atenção especial às mensagens automáticas e follow-ups.
Integração dos Canais de Aquisição e Anúncios Atualização
O cliente informou que os principais canais de aquisição são anúncios no Facebook e Instagram, com integração nativa disponível na plataforma para coleta de métricas.
Apesar de possuir cadastro em portais automotivos (Webmotors, etc.), o cliente destacou que as vendas provenientes desses canais são mínimas ou nulas.
A centralização dos leads de diferentes canais (incluindo potencial integração com Messenger e TikTok no futuro) foi mencionada, visando otimizar o fluxo de vendas.
Treinamento e Suporte na Implantação Decisão
Foi acordado que, em até uma semana, um calendário será enviado para agendar o primeiro treinamento com toda a equipe, garantindo que todos entendam o funcionamento da nova solução.
Um grupo oficial no WhatsApp foi definido como canal central para suporte, dúvidas, feedbacks e controle das tarefas durante a implementação.
O treinamento abordará não só as funcionalidades do CRM, mas também as integrações, automações e o uso da IA para aprimorar o atendimento.
Estrutura de Operação Comercial do Cliente Atualização
O cliente detalhou que a operação comercial é realizada por uma equipe enxuta composta por três pessoas (proprietário, um vendedor e um administrativo).
Informou que o fluxo de atendimento é gerenciado via WhatsApp, com o vendedor cuidando de todas as etapas, e que os anúncios são gerenciados internamente.
Os leads são majoritariamente originados por campanhas pagas nas redes sociais, e a abordagem varia conforme a localidade (atendimento presencial para Itajaí e atendimento diferenciado para outras regiões).
Outras Integrações e Funcionalidades da Plataforma Atualização
Além do Chat Guru, foi mencionado o uso do Revenda Mais e outras integrações que possibilitam centralização das informações dos leads e o acompanhamento do pipeline de vendas.
A solução também prevê futuras integrações com Instagram Messenger e TikTok, ampliando os canais de aquisição e atendimento.
Essas integrações contribuirão para a automação dos follow-ups, possibilitando que o vendedor foque em negociações e não no atendimento manual.

Transcript
Raul Behnke: E aí E aí E aí E aí E aí Boa tarde! Boa tarde! Conseguem me escutar? Teste, teste. Consegue me escutar?
AUTO VIP: Tá me ouvindo?
Raul Behnke: Opa, perfeitamente.
AUTO VIP: Agora sim, vamos abrir a câmera aqui também. Deu boa, deixa eu só chegar
Raul Behnke: no
AUTO VIP: meu escritório
Raul Behnke: aqui. Fechada. É o Michael, né?
AUTO VIP: Isso mesmo.
Raul Behnke: Perfeito, Michael.
AUTO VIP: Boa. Show
Raul Behnke: de bola. Vai ser só a gente mesmo nessa reunião? Ou é mais a gente alinhar as expectativas, mapear o processo comercial? Não,
AUTO VIP: primeiro acho que é só nós dois mesmo, depois
Raul Behnke: questão
AUTO VIP: de treinamento para o pessoal comercial, aí outra história,
Raul Behnke: né? Isso, isso, exatamente. Então, como eu estava falando, a gente vai mapear o processo comercial aqui, né? Alinhar alguns requisitos técnicos e explicar um pouco de como é a implantação em geral e te mostrar um pouco como que a gente vai fazer. Então, vou coletar essas informações. Primeiramente, prazer, acho que é o nosso primeiro contato ali fora do grupo, né? Vou
AUTO VIP: chamar
Raul Behnke: o Hugo, que é o responsável técnico pela implementação. A gente tem uma metodologia para realizar a implementação completa do sistema em até dois meses, divididas em três etapas. A primeira fase é a migração. A gente entende se você tem algum sistema que já usa cotidianamente, se já tem
AUTO VIP: uma
Raul Behnke: planilha de contatos, quais são todos os seus dados, quais são as integrações que você atualmente utiliza, onde que anuncia, etc. A gente faz essa migração para dentro do CRM da Azul. Esse primeiro passo se inicia hoje, a primeira etapa seria essa coleta de dados, o entendimento. Em até uma semana a gente marca o primeiro treinamento com a equipe, explicando o essencial da plataforma para que eles possam operar, onde o WhatsApp
AUTO VIP: já
Raul Behnke: vai estar conectado, onde já vai dar tudo certo para que eles possam atender os clientes e se organizar ali dentro do sistema. Então, leva em média uma semana. A parte do... A segunda etapa, a gente chama de desenvolvimento 1, o desenvolvimento das automações, é onde a gente começa a entender o cenário de vocês, quais que são tarefas repetitivas, se encaixa a questão dos follow-ups, das saudações automáticas. Então, a gente já vai mapear todo esse fluxo que acontece desde quando um cliente entra no marketplace, por exemplo, até o momento em que ele precisa receber um follow-up e essa cadência toda a gente desenha e automatiza dentro da plataforma. Então, isso em média mais três semanas, e por final, depois de que esteja tudo alinhado, toda a plataforma configurada, aí chega a parte da IA, onde a gente entende todo o seu processo de pré-qualificação. Então, desde que o cliente entra, quais são as perguntas essenciais, etc. e finaliza com a implementação, a gente faz um ambiente de teste para vocês testarem
AUTO VIP: a
Raul Behnke: IA, simulando que vocês são um lead, um cliente de exemplo, e depois, após validado, a gente já publica essa IA para atender os leads de vocês. Esse processo da IA é um pouco mais demorado, porque é personalizado conforme a empresa de vocês, então a gente vai entender como a empresa se posiciona, como ela se comunica, quais são o fluxo, qual é o estilo de comunicação e a gente vai traduzir tudo isso para uma IA. Então, esse processo fecha mais um mês, fechando os dois meses de implementação, iniciando hoje, perfeito? Então,
AUTO VIP: para
Raul Behnke: te entender, me explica um pouco sobre a AutoVIP, de onde vocês são, está há muito tempo nesse mercado?
AUTO VIP: A gente tem 20 anos de mercado já, 15 anos de mercado eu mais de 15 anos, são 17 anos de mercado, eu estava na região de Rio do Sul, Santa Catarina, agora eu estou aí fechando três anos aqui em Itajaí, que aí eu
Raul Behnke: transferi
AUTO VIP: a loja aqui para Itajaí, e a gente já
Raul Behnke: está
AUTO VIP: há três anos agora aqui em Itajaí, o meu fluxo maior aí é, posso dizer que 90%, 95% de fluxo de LEED é através de
Raul Behnke: campanha
AUTO VIP: de tráfico pago, Então... a gente hoje... direciona... na verdade... aí eu
Raul Behnke: tenho que
AUTO VIP: ver como é que vai
Raul Behnke: funcionar...
AUTO VIP: mas enfim... é que eu... hoje eu faço divulgação do lead aqui dentro de Itajaí... mais forte aqui dentro... Itajaí... navegantes... aqui na região...
Raul Behnke: mas
AUTO VIP: também abre o raio para Rio do Sul... quando é que era o meu... já era a minha carteira de lá... entende-se?
Raul Behnke: Então...
AUTO VIP: por exemplo... ontem à noite eu saí de lá... de Rio do Sul... porque eu vendi um carro lá...
Raul Behnke: Eu
AUTO VIP: tô com um cliente agora que me chamou de Laurentino que é da região lá então a gente
Raul Behnke: atende
AUTO VIP: as duas regiões só que quando o cliente é daqui de Itajaí a gente foca em fazer um agendamento para o cliente ir para a loja,
Raul Behnke: né? A gente
AUTO VIP: coloca aí para ver, tentar tirar algumas informações do cliente, se tem carro para dar na troca e tal.
Raul Behnke: E
AUTO VIP: o foco
Raul Behnke: principal
AUTO VIP: é trazer para o cliente, trazer para a loja. Já quando é uma cidade mais longe, que nem Rio de Sul, que já fica 130 quilômetros aí, então a gente já tem que ter um atendimento já mais diferenciado,
Raul Behnke: ir até no
AUTO VIP: valor de parcela e tudo mais,
Raul Behnke: né? No caso, hoje, vocês têm mais de uma loja, mais de um local ali?
AUTO VIP: Não, não. Tem só de Itajaí.
Raul Behnke: Só uma loja de Itajaí, uma unidade, né? É. O teu público são veículos um pouco mais tíquete
AUTO VIP: elevado? Popular.
Raul Behnke: Popular? Popular.
AUTO VIP: Hoje nós trabalhamos aí tíquete 60 mil, 50, 60 mil, né?
Raul Behnke: Vou
AUTO VIP: vender o base,
Raul Behnke: o carrinho
AUTO VIP: mais barato até ali Onix 25, HB20, 25, o popular semi novo né. É o mesmo
Raul Behnke: estilo
AUTO VIP: da NIC multimarcas. Não
Raul Behnke: entendo sim. Essa parte ali eu entendi bem como funciona. Existe a negociação à distância onde o cliente
AUTO VIP: chega,
Raul Behnke: ele quer Primeiro ver se aprova tudo, se a ficha dele passa, se o financiamento
AUTO VIP: dele passa.
Raul Behnke: Tá fechado, a gente negocia ele pra ir lá pra Rio do Sul. E quando, em Itajaí mesmo, a gente vai negociar uma visita pra chamar o cliente pra dentro da loja, pra ter essas vantagens, a persuasão de estar ali no presencial.
AUTO VIP: Então, entendo
Raul Behnke: assim, isso é o que a gente vai mapear mais pra frente, pra Eva ser bem interessante, ela ter noção disso. Então pelo que eu entendi ali o teu fluxo maior hoje vem de anúncios isso?
AUTO VIP: Isso mesmo.
Raul Behnke: Tu anuncia no Meta no caso Facebook,
AUTO VIP: Instagram,
Raul Behnke: Google também ou não?
AUTO VIP: Pelo gerenciador de anúncio né.
Raul Behnke: Mas Google também ou não?
AUTO VIP: Não Google não é Facebook, Instagram e Facebook e Instagram.
Raul Behnke: Então legal, a gente hoje tem a integração nativa com o Facebook, então a gente consegue ter todas essas métricas aqui dentro do
AUTO VIP: sistema.
Raul Behnke: Acredito que o Felipe já tenha te explicado isso, né? Hoje quando um lead entra, ele vai direto para o WhatsApp? Ele preenche um formulário?
AUTO VIP: Vai direto pro WhatsApp.
Raul Behnke: Vai direto pro WhatsApp.
AUTO VIP: Então geralmente
Raul Behnke: cai a mensagenzinha lá, oi, vim através desse anúncio, tô interessado em tal carro.
AUTO VIP: É, ele vem,
Raul Behnke: na
AUTO VIP: verdade, ele vem a
Raul Behnke: tela
AUTO VIP: já com que nem esse cliente aqui não acho que não vai conseguir ver que
Raul Behnke: tá desfocado
AUTO VIP: mas o cliente veio
Raul Behnke: aí
AUTO VIP: aparece aqui para mim qual não vai aparecer né
Raul Behnke: tá desfocando
AUTO VIP: aqui
Raul Behnke: mas
AUTO VIP: enfim aparece o anunciozinho aqui em cima
Raul Behnke: e
AUTO VIP: já vai um de que cidade você fala ele já respondeu que é de Laurentino e tal
Raul Behnke: e
AUTO VIP: aí
Raul Behnke: só
AUTO VIP: que aí ele cai dentro do meu chat guru vai pro meu pro meu pro meu CRM que é o chat guru aí ali dentro ele fica no aberto os que são
Raul Behnke: E
AUTO VIP: o que o meu vendedor atende ele já vai para o atendimento ou se o meu vendedor está esperando uma resposta do cliente ele fica lá não aguardando né. Se
Raul Behnke: o
AUTO VIP: cliente não responder no outro dia ele já puxa. Ele não vai mandar mensagem para o cliente mas ele puxa para o meu vendedor ver que
Raul Behnke: tem
AUTO VIP: que
Raul Behnke: chamar de novo.
AUTO VIP: Tem que chamar de novo.
Raul Behnke: E hoje tu pretende desativar esse chat guru e continuar só com as dois. A intenção
AUTO VIP: é essa né. pelo que foi me apresentado, estando dentro do...
Raul Behnke: A
AUTO VIP: gente consegue fazer aquela questão de agendamento de ligação e tudo mais, então acho que fica mais vantagem hoje em ter o CRM aí dentro, né?
Raul Behnke: Tá legal, com certeza. Então, show de bola. Eu vou te pedir o seguinte, se possível, criar um acesso pra mim dentro do chat Guru, pra eu já trazer as informações que você já tem armazenada dentro desse RM, pra eu já trazer pra cá, pra você não estar 100% no zero. Então,
AUTO VIP: ali já
Raul Behnke: vai ter todas as informações, as negociações, talvez a gente já extraia o que precisa de follow-up, o que tá novo, e já configurar também a entrada desses links automaticamente.
AUTO VIP: se
Raul Behnke: fosse possível me fornecer um acesso, se não, se conseguir extrair algum arquivo, algum tipo de arquivo.
AUTO VIP: Não, não, eu te
Raul Behnke: envio
AUTO VIP: o acesso, eu tenho o acesso meu mesmo, de administrador, que é mais fácil, porque aí tu entra dentro ali, entra como se fosse eu, e aí tu busca ali o que tu
Raul Behnke: precisa
AUTO VIP: de informação.
Raul Behnke: Perfeito. Hoje existe alguém interno aí na operação de vocês que faz os anúncios ou vocês têm algum gestor?
AUTO VIP: Eu mesmo
Raul Behnke: que faço. Você mesmo
AUTO VIP: que faz? Eu mesmo
Raul Behnke: que
AUTO VIP: faço.
Raul Behnke: Legal, show de bola. Eu pergunto isso porque geralmente quando é algum gestor externo, terceiro,
AUTO VIP: a gente pede
Raul Behnke: o contato dele pra gente criar um acesso pra ele, pra ele fazer todas as integrações necessárias, o mapeamento, tudo certinho. Mas como é você, a gente já fala contigo mesmo. Outra dúvida, falando de aquisição, os canais de aquisição, você trabalha também com portais automotivos, Webmotors, LX?
AUTO VIP: Tenho o Webmotors, Webmotors na pista e o Mobial, são os três que eu trabalho.
Raul Behnke: Hoje você gerencia o teu estoque, tem algum sistema que já traz
AUTO VIP: esses
Raul Behnke: vídeos automaticamente? Ou você tem que ir em cada plataforma e ver os vídeos que entraram?
AUTO VIP: Depende da mais, mas ele não vai para dentro da minha plataforma.
Raul Behnke: Ele
AUTO VIP: não vem por dentro desse chat. Ele não vem até porque eu não sou nada. Não vendo nada pelos portais. Eu só tenho os portais porque realmente sou obrigado a pagar. Mas por exemplo é motores eu nem anuncio não é motores. Eu não anuncio nada porque já era ali de caro não consigo converter ali. Então eu não é o meu forte os portais. Lógico aí a gente vai a gente vai fazer na pista e o A gente se der para configurar a gente configura ele para eles caírem ali para a gente também certo.
Raul Behnke: Não a gente consegue sim. A gente já tem integração com eles. Mas
AUTO VIP: as
Raul Behnke: vendas
AUTO VIP: por portal é zero.
Raul Behnke: É poucas, poucas. É nulas? É
AUTO VIP: nula, é nula. Olha, faz mais de ano que eu não vendi um carro por portal.
Raul Behnke: Nossa, interessante. Tem um pessoal que a gente trabalha que vende bastante por portal, mas como eu vi aqui, o teu forte mesmo é a moça.
AUTO VIP: É, eu sei
Raul Behnke: lá,
AUTO VIP: às vezes é um jeito de trabalhar também.
Raul Behnke: Isso, eu foco às vezes.
AUTO VIP: Perfeito.
Raul Behnke: Maiko, então falando na tua estrutura comercial hoje, quantos funcionários, vendedores você tem aí na tua operação?
AUTO VIP: Hoje nós estamos em três só aqui. É eu, um vendedor e uma pessoa no administrativo.
Raul Behnke: Então só três. Tem alguém que fica responsável? Existe alguma divisão de pré-atendente, vendas?
AUTO VIP: Ou já
Raul Behnke: cai, já atende, já negocia?
AUTO VIP: Vendedor faz tudo.
Raul Behnke: Então a ideia é que a IA se torne essa primeiro contato.
AUTO VIP: Esse
Raul Behnke: filtro,
AUTO VIP: é. Legal,
Raul Behnke: show de bola. Hoje você já provavelmente ali no chat guru, né?
AUTO VIP: Chat guru, isso
Raul Behnke: aí. Você já tem aquela visualização, que a gente chama de pipeline ou funil de vendas, com as etapas pré-determinadas, né? Às vezes pré-atendimento, agendamento, negociação. Isso você já tem pronto, já tem familiarizado?
AUTO VIP: Do this dentro do chat guru?
Raul Behnke: Isso, isso.
AUTO VIP: É, eu tenho uma divisão de como está o cliente no momento, entende-se? Ah, eu tenho relatório para puxar, se eu quiser, quantas mensagens forem enviadas, enfim, tem uma série de relatórios que dá para tirar ali dentro, sim.
Raul Behnke: Não, legal. Então, era mais isso, a parte de CRM hoje vocês já utilizam o Chat Guru e o Revenda Mais, coisa que a gente consegue já integrar bastante aqui, com
AUTO VIP: isso
Raul Behnke: a gente já tem bastante dados
AUTO VIP: para
Raul Behnke: partir com o uso do CRM de uma maneira melhor. Se falando de conexões de WhatsApp dentro da plataforma, vai ser necessário para os três, para os três colaboradores, vai ser necessário apenas um WhatsApp oficial da loja, algo do tipo?
AUTO VIP: Aqui eu trabalho com um WhatsApp só.
Raul Behnke: Cai todos
AUTO VIP: num WhatsApp só, porque como o próprio sistema ali divide para os vendedores,
Raul Behnke: Então
AUTO VIP: eu deixo por um no Whatsapp só
Raul Behnke: porque
AUTO VIP: o vendedor não atende não vai pro Whatsapp dele
Raul Behnke: ele
AUTO VIP: atende pelo Whatsapp da loja.
Raul Behnke: Perfeito legal. Outra questão Eu não sei como é que foi a negociação com o Felipe, só para entender, existe, não sei se provavelmente você já está alterado nisso, existem dois tipos de conexão com o WhatsApp, a API oficial,
AUTO VIP: que
Raul Behnke: pede a custo, né, com os templates,
AUTO VIP: etc.
Raul Behnke: E a API externa, você já definiu qual que vai ser a preferência?
AUTO VIP: Então vamos começar com a externa,
Raul Behnke: para
AUTO VIP: a gente modular e fazer um um levantamento do que que a gente vai mandar de mensagem, o que que a gente vai fazer de envios para ver se vai ter algum problema com banimento, porque eu já tive um problema com banimento agora recentemente também, então, mas a gente começa para testar e vamos ver, se tiver algum tipo de problema a gente passa para oficial aí.
Raul Behnke: Legal, aqui na Zui a gente toma bastante cuidado com essa questão, cuidado qualidade de entrega referente a PI externa porque existe muito esse risco. O banimento em si é algo que foge do nosso controle mas a gente tem medidas para evitar.
AUTO VIP: Eu só para ter uma ideia estou tomando o banimento aqui mas é
Raul Behnke: e
AUTO VIP: eu não faço não faço disparo. Eu não
Raul Behnke: faço disparo.
AUTO VIP: é por exemplo teve um final de semana teve um final de semana um sábado e domingo aqui que a gente recebeu chegou na segunda-feira tinha 100 leads para atender 100 e
Raul Behnke: aí
AUTO VIP: cara
Raul Behnke: vai
AUTO VIP: respondendo todo mundo aí falando tudo certo como é que tá babá e chegou seis horas da tarde e caiu a
Raul Behnke: conta. Aí
AUTO VIP: depois lógico volta mas fica ali às vezes 24 horas 48 horas
Raul Behnke: sem atendimento né. É outra coisa que eu esqueci de perguntar você trabalha também no Instagram algo do tipo conversa por lá ou não?
AUTO VIP: Tudo pelo Whatsapp tá
Raul Behnke: mas
AUTO VIP: são questões que a gente pode tratar isso para ver se tem a possibilidade de fazer porque automaticamente o custo é mais barato também né se a gente é se a gente bota uma campanha para ir para o Messenger para ir para o porque agora tem
Raul Behnke: uma
AUTO VIP: nova campanha ali dentro que tu consegue fazer, onde tu gera engajamento e conversa. Tu bota
Raul Behnke: os três juntos
AUTO VIP: ali e ele se torna um lead mais barato, vamos dizer assim,
Raul Behnke: né?
AUTO VIP: Isso,
Raul Behnke: claro. Aqui dentro da Zoio a gente tem o Omnichannel, que a gente chama.
AUTO VIP: Ele
Raul Behnke: centraliza todas as conversas. Então, por exemplo, você tem um lead que veio pelo Instagram, iniciou
AUTO VIP: conversando
Raul Behnke: com ele e depois, vamos supor, ali na etapa de negociação
AUTO VIP: começou
Raul Behnke: a tratar pelo WhatsApp, né?
AUTO VIP: Você
Raul Behnke: tem toda essa centralização dentro do sistema. No treinamento eu vou mostrar bem certinho isso. A gente consegue conectar aqui tanto o Facebook quanto o Messenger. Caso futuramente for fazer anúncios no TikTok tenha a possibilidade também. Então é extremamente interessante. Mas beleza, Michael, eu tô gravando essa reunião, tá? Era o essencial, é só pra entender bem o funcionário. A gente começou
AUTO VIP: a
Raul Behnke: montar aqui o sistema, tá?
AUTO VIP: O
Raul Behnke: canal oficial vai ser o grupo do WhatsApp,
AUTO VIP: tá?
Raul Behnke: A gente vai centralizar todas as dúvidas por ali, o suporte em geral. E também
AUTO VIP: o
Raul Behnke: controle das tarefas, os feedbacks que eu vou te passando conforme a gente vai implementando vai ser tudo. pelo que eu entendi é que a gente busca definir um ponto focal para comunicação, então geralmente a gente seleciona um colaborador que vai ficar à frente do
AUTO VIP: sistema,
Raul Behnke: a
AUTO VIP: gente vai
Raul Behnke: dar um suporte
AUTO VIP: mais
Raul Behnke: próximo para que ele
AUTO VIP: seja
Raul Behnke: o nosso embaixador dentro da empresa. Então acredito que como você já tem noção do sistema de anúncios, já está para assistir, o materializado provavelmente vai ser contigo mesmo.
AUTO VIP: Isso,
Raul Behnke: vai passar por
AUTO VIP: mim. a
Raul Behnke: gente vai tendo essa confirmação. Mas beleza, então. Seria isso, eu vou te atualizando sobre as tarefas. Em até uma semana eu já te mando o calendário novamente pra gente marcar o treinamento com a tua equipe completa.
AUTO VIP: Então
Raul Behnke: a gente inicia essa primeira fase de integração, de migração. Trazer todos os dados, depois a gente inicia as fases pra ver o que é automação, o que a gente pode fazer automaticamente, follow up. Sem precisar que o vendedor gaste tempo lá e faça manualmente. E depois a gente segue para a nossa conversa de IA para tratar toda essa questão
AUTO VIP: da comunicação.
Raul Behnke: Legal?
AUTO VIP: Te mandei na conversa aí já o link, o e-mail e... Desculpa. Login e senha para tu poder entrar no chat Guru ali.
Raul Behnke: Perfeito.
AUTO VIP: Show
Raul Behnke: de bola. Tudo isso que eu preciso. Então, Michael, se tiver qualquer dúvida, não sei se tem alguma dúvida agora.
AUTO VIP: Qualquer
Raul Behnke: coisa
AUTO VIP: é
Raul Behnke: só mandar no grupo ali que a gente está disponível, tá bom?
AUTO VIP: Fechou então. Obrigado,
Raul Behnke: querido. Michael, muito obrigado. Tenha um bom dia. Tchau, tchau.
AUTO VIP: Tchau, tchau. Bom dia.