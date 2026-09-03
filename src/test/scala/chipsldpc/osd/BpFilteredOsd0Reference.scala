package chipsldpc.osd

import chipsldpc.{Gf2Reference, Reference}
import chipsldpc.sort.{MagnitudeAscending, SignedAscending}

private[osd] final case class BpFilteredOsd0Expected(
    status: Int,
    iterations: Int,
    cycles: Int,
    bpCycles: Int,
    osdCycles: Int,
    selected: Int,
    activeRows: Int,
    solverCycles: Int,
    eligible: Int,
    soft: Vector[Int],
    correction: Vector[(Int, Int)],
)

/** Independent BP and ascending-pivot GF(2) model for one decoder frame. */
private[osd] object BpFilteredOsd0Reference {
  def run(
      config: BpFilteredOsd0Config,
      prior: Vector[Int],
      syndrome: Vector[Boolean],
      scope: Option[Set[Int]] = None,
  ): BpFilteredOsd0Expected = {
    val graph = config.graph
    var state = Reference.initialize(config.nodes, prior, config.q)
    var converged = Option.empty[Int]
    for (iteration <- 1 to config.iterations if converged.isEmpty) {
      state = Reference.iterate(
        config.nodes, state, syndrome, prior,
        iteration.min((1 << config.scale.controlBits) - 1), config.q, config.scale,
      )
      if (!Reference.residual(config.nodes, state, syndrome).contains(true))
        converged = Some(iteration)
    }

    val eligible = state.marginal.indices.filter(i => (config.order match {
      case MagnitudeAscending => state.marginal(i).abs < config.threshold
      case SignedAscending => state.marginal(i) < config.threshold
    }) && scope.forall(_(i))).sortBy(i => (
      if (config.order == MagnitudeAscending) state.marginal(i).abs else state.marginal(i), i,
    )).toVector
    converged match {
      case Some(iterations) =>
        val bpCycles = 2 * iterations
        BpFilteredOsd0Expected(
          0, iterations, bpCycles + 1 + graph.variableCount, bpCycles,
          0, 0, 0, 0, eligible.size, state.marginal,
          state.decision.indices.map(i => i -> (if (state.decision(i)) 1 else 0)).toVector,
        )
      case None => fallback(config, syndrome, state.marginal, eligible)
    }
  }

  private def fallback(
      config: BpFilteredOsd0Config,
      syndrome: Vector[Boolean],
      soft: Vector[Int],
      eligible: Vector[Int],
  ): BpFilteredOsd0Expected = {
    val graph = config.graph
    val kept = eligible.take(config.osd.maxSelected)
    val overflow = eligible.size > config.osd.maxSelected
    val rejected = overflow && config.rejectOverflow

    def solve(columns: Vector[Int], width: Int) = {
      val rows = Array.fill(graph.checkCount)(BigInt(0))
      for (slot <- columns.indices; row <- graph.colOnes(columns(slot)))
        rows(row) = rows(row).setBit(slot)
      val activeRows = rows.indices.count(row => rows(row) != 0 || syndrome(row))
      val solved = Gf2Reference.solveBig(rows.toVector, syndrome.map(if (_) 1 else 0), columns.size)
      val cycles = if (activeRows == 0) 0 else activeRows + 3 * width + 1
      (solved, activeRows, cycles)
    }

    val sorterCycles = graph.variableCount + eligible.size
    var attempt = 0
    var selected = kept.take(config.prefixes.head)
    var solved = solve(selected, config.prefixes.head)
    if (rejected) return BpFilteredOsd0Expected(
      3, config.iterations, 2 * config.iterations + 1 + sorterCycles,
      2 * config.iterations, sorterCycles, selected.size, solved._2, 0,
      eligible.size, soft, Vector.empty,
    )
    var solverCycles = solved._3
    while (!solved._1.consistent && attempt + 1 < config.prefixes.size &&
           kept.size > config.prefixes(attempt)) {
      attempt += 1
      selected = kept.take(config.prefixes(attempt))
      solved = solve(selected, config.prefixes(attempt))
      solverCycles += solved._3
    }
    val (result, activeRows, _) = solved
    val consistent = result.consistent
    val osdCycles = if (activeRows == 0) sorterCycles + 3 else
      sorterCycles + solverCycles + 4 * attempt +
        (if (consistent) selected.size + 2 else 3)
    val status = if (consistent) 1 else 2
    BpFilteredOsd0Expected(
      status, config.iterations, 2 * config.iterations + 1 + osdCycles,
      2 * config.iterations, osdCycles, selected.size, activeRows, solverCycles,
      eligible.size, soft,
      if (consistent) selected.zip(result.bits) else Vector.empty,
    )
  }
}
