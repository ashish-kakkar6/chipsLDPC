package chipsldpc

import chipsldpc.graph.TannerNodeGraphs

object Reference {
  final case class SignMag(sign: Boolean, magnitude: Int) {
    def signed: Int = if (sign && magnitude != 0) -magnitude else magnitude
  }
  final case class MinPair(first: Int, second: Int)
  final case class EdgeMeta(sign: Boolean, useSecond: Boolean)
  final case class CheckResult(minima: MinPair, edges: Seq[EdgeMeta])
  final case class CheckMessage(minima: MinPair, sign: Boolean, useSecond: Boolean) {
    def signed: Int = SignMag(sign, if (useSecond) minima.second else minima.first).signed
  }
  final case class VariableResult(marginal: Int, decision: Boolean, extrinsic: Seq[SignMag])
  final case class DecoderState(v2c: Vector[SignMag], marginal: Vector[Int], decision: Vector[Boolean])

  def twoMin(values: Seq[Int]): MinPair = {
    val sorted = values.sorted
    MinPair(sorted(0), sorted(1))
  }

  private def maximum(bits: Int): Int = (1 << bits) - 1

  def scale(value: Int, control: Int, policy: CheckScale, bits: Int): Int = policy match {
    case NoScale          => value
    case VallsScale(a, b) => ((value >> a) + (value >> b)).min(maximum(bits))
    case RampScale(limit) => if (control <= limit) value - (value >> control) else value
  }

  def check(inputs: Seq[SignMag], syndrome: Boolean, control: Int, config: CheckConfig): CheckResult = {
    val minima = twoMin(inputs.map(_.magnitude))
    val scaled = MinPair(
      scale(minima.first, control, config.scale, config.q.magnitudeBits),
      scale(minima.second, control, config.scale, config.q.magnitudeBits),
    )
    val parity = inputs.foldLeft(syndrome)((p, x) => p ^ (x.sign && x.magnitude != 0))
    val edges = inputs.map { input =>
      val useSecond = input.magnitude == minima.first
      EdgeMeta(parity ^ (input.sign && input.magnitude != 0), useSecond)
    }
    CheckResult(scaled, edges)
  }

  private def clip(value: Int, bits: Int): Int =
    value.max(-(1 << (bits - 1))).min((1 << (bits - 1)) - 1)

  private def signMag(value: Int, bits: Int): SignMag = {
    val magnitude = value.abs.min(maximum(bits))
    SignMag(value < 0 && magnitude != 0, magnitude)
  }

  def hardDecision(value: Int): Boolean = value < 0

  def variable(inputs: Seq[CheckMessage], prior: Int, config: VariableConfig): VariableResult = {
    val messages = inputs.map(_.signed)
    val total = prior + messages.sum
    VariableResult(
      clip(total, config.q.accumulatorBits),
      hardDecision(total),
      messages.map(message => signMag(total - message, config.q.magnitudeBits)),
    )
  }

  def relayBias(prior: Int, previous: Int, beta: Int, format: RelayFormat, q: Quantization): Int = {
    val scaledPrior = (BigInt(prior) * beta) >> format.fractionalBits
    val scaledPrevious = (BigInt(previous) * beta) >> format.fractionalBits
    clip((scaledPrior + previous - scaledPrevious).toInt, q.accumulatorBits)
  }

  def initialize(nodes: TannerNodeGraphs, priors: Seq[Int], q: Quantization): DecoderState = {
    require(priors.size == nodes.graph.variableCount)
    require(priors.forall(p => p >= 0 && p <= maximum(q.magnitudeBits)))
    DecoderState(
      nodes.graph.edges.map(edge => SignMag(false, priors(edge.variable))),
      priors.map(clip(_, q.accumulatorBits)).toVector,
      Vector.fill(priors.size)(false),
    )
  }

  def iterate(
      nodes: TannerNodeGraphs,
      state: DecoderState,
      syndrome: Seq[Boolean],
      priors: Seq[Int],
      control: Int,
      q: Quantization,
      scalePolicy: CheckScale,
  ): DecoderState = {
    require(syndrome.size == nodes.graph.checkCount && state.v2c.size == nodes.graph.edgeCount)
    val checks = nodes.checks.map { node =>
      check(
        node.edges.map(edge => state.v2c(edge.edgeId)),
        syndrome(node.checkId),
        control,
        CheckConfig(node.degree, q, scalePolicy),
      )
    }
    val variables = nodes.variables.map { node =>
      val messages = node.edges.map { edge =>
        val port = nodes.connections(edge.edgeId).checkPort
        val result = checks(edge.checkId)
        CheckMessage(result.minima, result.edges(port).sign, result.edges(port).useSecond)
      }
      variable(messages, priors(node.variableId), VariableConfig(node.degree, q))
    }
    val v2c = nodes.connections.map { edge =>
      variables(edge.variableId).extrinsic(edge.variablePort)
    }
    DecoderState(v2c, variables.map(_.marginal), variables.map(_.decision))
  }

  def residual(nodes: TannerNodeGraphs, state: DecoderState, syndrome: Seq[Boolean]): Vector[Boolean] =
    nodes.graph.rowOnes.zip(syndrome).map { case (row, bit) =>
      row.foldLeft(bit)((parity, variable) => parity ^ state.decision(variable))
    }
}
