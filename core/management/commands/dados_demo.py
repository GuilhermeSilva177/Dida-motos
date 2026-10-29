import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import PerfilUsuario
from fornecedores.models import Fornecedor, HistoricoCompra
from movimentacoes.models import Movimentacao
from ordens_servico.models import Cliente, ItemOrdemServico, Motocicleta, OrdemServico
from pecas.models import Categoria, Fabricante, Localizacao, ModeloMoto, Peca


class Command(BaseCommand):
    help = (
        "Popula o sistema com dados de exemplo (peças, clientes, veículos, "
        "fornecedores, movimentações e ordens de serviço) para demonstração/"
        "apresentação. Idempotente: pode ser rodado de novo sem duplicar nada "
        "(usa get_or_create pelas chaves naturais e para antes de criar OS/"
        "movimentações se já existirem dados de demo)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Remove os dados de demo criados por este comando antes de recriá-los.",
        )

    def handle(self, *args, **options):
        if options["limpar"]:
            self._limpar()

        with transaction.atomic():
            self.usuarios = self._criar_usuarios()
            self.categorias = self._criar_categorias()
            self.fabricantes = self._criar_fabricantes()
            self.localizacoes = self._criar_localizacoes()
            self.modelos_moto = self._criar_modelos_moto()
            self.pecas = self._criar_pecas()
            self.fornecedores = self._criar_fornecedores()
            self._criar_historico_compras()
            self.clientes = self._criar_clientes_e_motos()
            self._criar_movimentacoes_historico()
            self._criar_ordens_servico()

        self.stdout.write(self.style.SUCCESS(
            "\nDados de demonstração criados com sucesso!\n"
            "Contas de funcionário de exemplo (senha para todas: Demo@1234):\n"
            "  gerente.demo   (grupo Gerentes)\n"
            "  mecanico.demo  (grupo Mecânicos)\n"
        ))

    # ------------------------------------------------------------------
    # Limpeza (opcional, para poder rodar de novo numa apresentação)
    # ------------------------------------------------------------------
    def _limpar(self):
        self.stdout.write("Removendo dados de demo anteriores...")

        # Ordens de serviço: apaga item a item (isso aciona o delete()
        # customizado de ItemOrdemServico, que reverte o estoque e remove
        # a movimentação ligada) antes de apagar a própria OS. Um delete
        # em massa no queryset pularia essa lógica e deixaria o estoque
        # descontado para sempre.
        for os_ in OrdemServico.objects.filter(cliente__cpf__in=self._cpfs_demo()):
            for item in os_.itens.all():
                item.delete()
            os_.delete()

        Motocicleta.objects.filter(cliente__cpf__in=self._cpfs_demo()).delete()
        Cliente.objects.filter(cpf__in=self._cpfs_demo()).delete()

        # Mesmo motivo acima: apaga uma movimentação por vez para que o
        # delete() customizado devolva a quantidade ao estoque da peça.
        for mov in Movimentacao.objects.filter(observacao__startswith="[demo]"):
            mov.delete()

        HistoricoCompra.objects.filter(fornecedor__nome__in=self._nomes_fornecedores_demo()).delete()
        Fornecedor.objects.filter(nome__in=self._nomes_fornecedores_demo()).delete()
        Peca.objects.filter(codigo__startswith="DEMO-").delete()
        for username in ["gerente.demo", "mecanico.demo"]:
            User.objects.filter(username=username).delete()

    def _cpfs_demo(self):
        return [c[1] for c in self._dados_clientes()]

    def _nomes_fornecedores_demo(self):
        return [f[0] for f in self._dados_fornecedores()]

    # ------------------------------------------------------------------
    # Funcionários de demonstração
    # ------------------------------------------------------------------
    def _criar_usuarios(self):
        grupo_gerentes, _ = Group.objects.get_or_create(name="Gerentes")
        grupo_mecanicos, _ = Group.objects.get_or_create(name="Mecânicos")

        usuarios = []
        for username, first_name, last_name, grupo, is_staff in [
            ("gerente.demo", "Gerente", "Demo", grupo_gerentes, True),
            ("mecanico.demo", "Mecânico", "Demo", grupo_mecanicos, False),
        ]:
            user, criado = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_staff": is_staff,
                },
            )
            if criado:
                user.set_password("Demo@1234")
                user.save()
                user.groups.add(grupo)
                PerfilUsuario.objects.get_or_create(user=user, defaults={"deve_trocar_senha": False})
            usuarios.append(user)
        return usuarios

    # ------------------------------------------------------------------
    # Cadastros base de peças
    # ------------------------------------------------------------------
    def _criar_categorias(self):
        nomes = [
            ("Motor", "Peças do motor e componentes internos"),
            ("Transmissão", "Embreagem, corrente, coroa e pinhão"),
            ("Suspensão", "Amortecedores, molas e buchas"),
            ("Freios", "Pastilhas, discos e fluídos de freio"),
            ("Pneus", "Pneus e câmaras de ar"),
            ("Elétrica", "Baterias, velas e componentes elétricos"),
            ("Consumíveis", "Óleos, filtros e itens de manutenção periódica"),
            ("Acessórios", "Itens de personalização e conforto"),
        ]
        categorias = {}
        for nome, descricao in nomes:
            cat, _ = Categoria.objects.get_or_create(nome=nome, defaults={"descricao": descricao})
            categorias[nome] = cat
        return categorias

    def _criar_fabricantes(self):
        nomes = ["Honda", "Yamaha", "NGK", "Pirelli", "Motul", "Magnetron", "Sabó", "DID"]
        fabricantes = {}
        for nome in nomes:
            fab, _ = Fabricante.objects.get_or_create(nome=nome)
            fabricantes[nome] = fab
        return fabricantes

    def _criar_localizacoes(self):
        dados = [
            ("A", "01", "Motor"),
            ("A", "02", "Transmissão"),
            ("B", "01", "Suspensão e Freios"),
            ("B", "02", "Elétrica"),
            ("C", "01", "Consumíveis"),
        ]
        localizacoes = []
        for prateleira, caixa, setor in dados:
            loc, _ = Localizacao.objects.get_or_create(
                prateleira=prateleira, caixa=caixa, setor=setor
            )
            localizacoes.append(loc)
        return localizacoes

    def _criar_modelos_moto(self):
        dados = [
            ("Honda", "CG 160"),
            ("Honda", "Biz 125"),
            ("Honda", "PCX 150"),
            ("Yamaha", "Fazer 250"),
            ("Yamaha", "Factor 125"),
        ]
        modelos = []
        for marca, modelo in dados:
            m, _ = ModeloMoto.objects.get_or_create(marca=marca, modelo=modelo)
            modelos.append(m)
        return modelos

    def _dados_pecas(self):
        # codigo, nome, categoria, fabricante, qtd_estoque, qtd_minima, preco_custo, preco_venda
        return [
            ("DEMO-0001", "Vela de ignição NGK CR8E", "Elétrica", "NGK", 40, 10, 12.00, 24.90),
            ("DEMO-0002", "Óleo motor 10W30 1L", "Consumíveis", "Motul", 60, 15, 18.00, 32.00),
            ("DEMO-0003", "Filtro de óleo CG 160", "Consumíveis", "Honda", 25, 8, 9.50, 19.90),
            ("DEMO-0004", "Filtro de ar Biz 125", "Consumíveis", "Honda", 20, 6, 14.00, 27.50),
            ("DEMO-0005", "Pastilha de freio dianteira", "Freios", "Sabó", 15, 5, 22.00, 44.90),
            ("DEMO-0006", "Disco de freio CG 160", "Freios", "Honda", 8, 4, 65.00, 119.90),
            ("DEMO-0007", "Amortecedor traseiro par", "Suspensão", "Honda", 6, 3, 110.00, 199.90),
            ("DEMO-0008", "Pneu traseiro 80/100-18", "Pneus", "Pirelli", 12, 4, 85.00, 159.90),
            ("DEMO-0009", "Pneu dianteiro 2.75-18", "Pneus", "Pirelli", 14, 4, 70.00, 134.90),
            ("DEMO-0010", "Kit relação (corrente/coroa/pinhão)", "Transmissão", "DID", 10, 3, 95.00, 179.90),
            ("DEMO-0011", "Cabo de embreagem universal", "Transmissão", None, 18, 5, 15.00, 29.90),
            ("DEMO-0012", "Bateria 5Ah selada", "Elétrica", "Magnetron", 7, 3, 95.00, 169.90),
            ("DEMO-0013", "Lâmpada farol H4", "Elétrica", None, 30, 10, 11.00, 22.90),
            ("DEMO-0014", "Retrovisor universal (par)", "Acessórios", None, 2, 5, 28.00, 54.90),
            ("DEMO-0015", "Manopla de guidão (par)", "Acessórios", None, 3, 4, 19.00, 36.90),
        ]

    def _criar_pecas(self):
        pecas = {}
        for i, (codigo, nome, categoria, fabricante, qtd, qtd_min, custo, venda) in enumerate(
            self._dados_pecas()
        ):
            peca, criado = Peca.objects.get_or_create(
                codigo=codigo,
                defaults={
                    "nome": nome,
                    "categoria": self.categorias[categoria],
                    "fabricante": self.fabricantes[fabricante] if fabricante else None,
                    "quantidade_estoque": 0,  # ajustado via Movimentacao abaixo
                    "quantidade_minima": qtd_min,
                    "preco_custo": Decimal(str(custo)),
                    "preco_venda": Decimal(str(venda)),
                    "localizacao": self.localizacoes[i % len(self.localizacoes)],
                },
            )
            if criado:
                peca.modelos_compativeis.add(*self.modelos_moto[: (i % 3) + 1])
            peca._qtd_estoque_inicial = qtd
            pecas[codigo] = peca
        return pecas

    # ------------------------------------------------------------------
    # Fornecedores
    # ------------------------------------------------------------------
    def _dados_fornecedores(self):
        return [
            ("Distribuidora Motopeças SP", "Carlos Andrade", "(16) 3253-1010", "vendas@motopecas-sp.com.br", "Monte Alto - SP", 5),
            ("Honda Peças Originais Ribeirão", "Fernanda Lima", "(16) 3911-2020", "comercial@hondaribeirao.com.br", "Ribeirão Preto - SP", 3),
            ("Pneus & Cia Taquaritinga", "Marcos Souza", "(16) 3252-3030", "contato@pneusecia.com.br", "Taquaritinga - SP", 7),
        ]

    def _criar_fornecedores(self):
        fornecedores = {}
        for nome, contato, telefone, email, local, prazo in self._dados_fornecedores():
            forn, _ = Fornecedor.objects.get_or_create(
                nome=nome,
                defaults={
                    "contato_nome": contato,
                    "telefone": telefone,
                    "email": email,
                    "localizacao": local,
                    "prazo_entrega_dias": prazo,
                },
            )
            fornecedores[nome] = forn
        return fornecedores

    def _criar_historico_compras(self):
        nomes_fornecedores = list(self.fornecedores.keys())
        codigos_pecas = list(self.pecas.keys())
        combinacoes = [
            (nomes_fornecedores[0], codigos_pecas[0], HistoricoCompra.Tipo.COMPRA, 20, 11.50),
            (nomes_fornecedores[0], codigos_pecas[1], HistoricoCompra.Tipo.COMPRA, 30, 17.00),
            (nomes_fornecedores[1], codigos_pecas[2], HistoricoCompra.Tipo.COMPRA, 15, 9.00),
            (nomes_fornecedores[1], codigos_pecas[5], HistoricoCompra.Tipo.COTACAO, 4, 62.00),
            (nomes_fornecedores[2], codigos_pecas[7], HistoricoCompra.Tipo.COMPRA, 10, 80.00),
            (nomes_fornecedores[2], codigos_pecas[8], HistoricoCompra.Tipo.COTACAO, 10, 68.00),
        ]
        for nome_forn, codigo_peca, tipo, qtd, preco in combinacoes:
            HistoricoCompra.objects.get_or_create(
                fornecedor=self.fornecedores[nome_forn],
                peca=self.pecas[codigo_peca],
                tipo=tipo,
                defaults={"quantidade": qtd, "preco_unitario": Decimal(str(preco))},
            )

    # ------------------------------------------------------------------
    # Clientes e motocicletas
    # ------------------------------------------------------------------
    def _dados_clientes(self):
        # nome, cpf, telefone, email, [(marca, modelo, ano, placa), ...]
        return [
            ("João Pereira Silva", "39053344705", "(16) 99122-3344", "joao.pereira@email.com",
             [("Honda", "CG 160", 2021, "ABC1D23")]),
            ("Maria Oliveira Santos", "93541134780", "(16) 99233-4455", "maria.santos@email.com",
             [("Honda", "Biz 125", 2019, "DEF4E56")]),
            ("Pedro Henrique Costa", "11144477735", "(16) 99344-5566", "pedro.costa@email.com",
             [("Yamaha", "Fazer 250", 2022, "GHI7F89")]),
            ("Ana Carolina Souza", "52998224725", "(16) 99455-6677", "ana.souza@email.com",
             [("Honda", "PCX 150", 2023, "JKL0G12")]),
            ("Lucas Gabriel Almeida", "96995294580", "(16) 99566-7788", "lucas.almeida@email.com",
             [("Yamaha", "Factor 125", 2020, "MNO3H45")]),
            ("Fernanda Ribeiro Martins", "81837231010", "(16) 99677-8899", "fernanda.martins@email.com",
             [("Honda", "CG 160", 2018, "PQR6I78"), ("Honda", "Biz 125", 2022, "STU9J01")]),
        ]

    def _criar_clientes_e_motos(self):
        clientes = {}
        for nome, cpf, telefone, email, motos in self._dados_clientes():
            cliente, _ = Cliente.objects.get_or_create(
                cpf=cpf,
                defaults={"nome": nome, "telefone": telefone, "email": email},
            )
            for marca, modelo, ano, placa in motos:
                Motocicleta.objects.get_or_create(
                    cliente=cliente, placa=placa,
                    defaults={"marca": marca, "modelo": modelo, "ano": ano},
                )
            clientes[cpf] = cliente
        return clientes

    # ------------------------------------------------------------------
    # Movimentações: estoque inicial + histórico dos últimos 14 dias
    # ------------------------------------------------------------------
    def _criar_movimentacoes_historico(self):
        gerente = self.usuarios[0]
        agora = timezone.now()

        # Estoque inicial de cada peça, via Movimentacao (nunca setando
        # quantidade_estoque direto), com data recuada para parecer que a
        # loja já operava antes do período mostrado no gráfico.
        for peca in self.pecas.values():
            qtd_inicial = getattr(peca, "_qtd_estoque_inicial", 0)
            if qtd_inicial <= 0 or peca.movimentacoes.exists():
                continue
            mov = Movimentacao(
                peca=peca,
                tipo=Movimentacao.Tipo.ENTRADA,
                motivo=Movimentacao.Motivo.RECEBIMENTO_FORNECEDOR,
                quantidade=qtd_inicial,
                usuario=gerente,
                observacao="[demo] Estoque inicial",
            )
            mov.full_clean()
            mov.save()
            Movimentacao.objects.filter(pk=mov.pk).update(data=agora - timedelta(days=20))

        # Pequenas entradas/ajustes espalhados pelos últimos 14 dias, para
        # dar volume ao gráfico do dashboard. Só roda na primeira vez
        # (idempotência: sem isso, rodar o comando de novo sem --limpar
        # ficaria adicionando mais eventos aleatórios a cada execução).
        if Movimentacao.objects.filter(
            observacao__in=["[demo] Reposição de estoque", "[demo] Contagem de inventário"]
        ).exists():
            return
        # DEMO-0014 e DEMO-0015 nascem com estoque abaixo do mínimo de
        # propósito (ver _dados_pecas) para mostrar o alerta de estoque
        # baixo na apresentação — ficam fora do sorteio para não serem
        # "repostas" por uma entrada aleatória.
        codigos = [c for c in self.pecas.keys() if c not in ("DEMO-0014", "DEMO-0015")]
        random.seed(42)
        for dias_atras in range(13, -1, -1):
            qtd_eventos = random.randint(1, 3)
            for _ in range(qtd_eventos):
                codigo = random.choice(codigos)
                peca = self.pecas[codigo]
                tipo_evento = random.choice(["entrada", "entrada", "ajuste"])
                if tipo_evento == "entrada":
                    mov = Movimentacao(
                        peca=peca,
                        tipo=Movimentacao.Tipo.ENTRADA,
                        motivo=Movimentacao.Motivo.RECEBIMENTO_FORNECEDOR,
                        quantidade=random.randint(2, 8),
                        usuario=gerente,
                        observacao="[demo] Reposição de estoque",
                    )
                else:
                    mov = Movimentacao(
                        peca=peca,
                        tipo=Movimentacao.Tipo.AJUSTE,
                        motivo=Movimentacao.Motivo.INVENTARIO,
                        quantidade=random.randint(1, 2),
                        direcao_ajuste=Movimentacao.DirecaoAjuste.REDUCAO,
                        usuario=gerente,
                        observacao="[demo] Contagem de inventário",
                    )
                try:
                    mov.full_clean()
                except Exception:
                    continue
                mov.save()
                data_evento = agora - timedelta(days=dias_atras, hours=random.randint(8, 18))
                Movimentacao.objects.filter(pk=mov.pk).update(data=data_evento)

    # ------------------------------------------------------------------
    # Ordens de serviço
    # ------------------------------------------------------------------
    def _criar_ordens_servico(self):
        if OrdemServico.objects.filter(descricao_problema__startswith="[demo]").exists():
            return

        mecanico = self.usuarios[1]
        clientes = list(self.clientes.values())
        agora = timezone.now()

        cenarios = [
            # cliente_idx, status, descricao, dias_atras_abertura, [(codigo_peca, qtd)], concluida
            (0, OrdemServico.Status.ENTREGUE,
             "[demo] Troca de óleo e filtro, revisão geral.",
             12, [("DEMO-0002", 1), ("DEMO-0003", 1)], True),
            (1, OrdemServico.Status.ENTREGUE,
             "[demo] Troca de pastilhas de freio dianteiras, cliente relatou ruído ao frear.",
             9, [("DEMO-0005", 1)], True),
            (2, OrdemServico.Status.CONCLUIDA,
             "[demo] Revisão de corrente e troca de kit de relação.",
             5, [("DEMO-0010", 1), ("DEMO-0002", 1)], True),
            (3, OrdemServico.Status.EM_ANDAMENTO,
             "[demo] Troca de bateria, moto não estava pegando.",
             2, [("DEMO-0012", 1)], False),
            (4, OrdemServico.Status.AGUARDANDO_PECA,
             "[demo] Amortecedor traseiro vazando óleo, aguardando peça do fornecedor.",
             1, [], False),
            (5, OrdemServico.Status.ABERTA,
             "[demo] Cliente relatou barulho na suspensão dianteira, diagnóstico pendente.",
             0, [], False),
        ]

        for cliente_idx, status, descricao, dias_atras, itens, concluida in cenarios:
            cliente = clientes[cliente_idx]
            motocicleta = cliente.motocicletas.first()
            if motocicleta is None:
                continue

            valor_servico = Decimal("50.00") if itens else Decimal("0.00")
            os_ = OrdemServico(
                cliente=cliente,
                motocicleta=motocicleta,
                mecanico=mecanico,
                status=status,
                descricao_problema=descricao,
                valor_servico=valor_servico,
            )
            os_.save()
            data_abertura = agora - timedelta(days=dias_atras)
            OrdemServico.objects.filter(pk=os_.pk).update(data_abertura=data_abertura)

            for codigo_peca, qtd in itens:
                peca = self.pecas[codigo_peca]
                item = ItemOrdemServico(
                    ordem_servico=os_,
                    peca=peca,
                    quantidade=qtd,
                    preco_unitario=peca.preco_venda,
                )
                item._usuario_evento = mecanico
                item.save()
                if item.movimentacao_id:
                    Movimentacao.objects.filter(pk=item.movimentacao_id).update(data=data_abertura)

            if concluida:
                OrdemServico.objects.filter(pk=os_.pk).update(
                    status=status, data_conclusao=data_abertura + timedelta(days=1)
                )
