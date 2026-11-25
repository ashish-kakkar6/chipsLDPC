package chipsldpc

import chipsldpc.graph.{TannerGraph, TannerNodeGraphs}
import java.nio.file.{Files, Paths}
import org.scalatest.freespec.AnyFreeSpec

/** Replay the immutable animation numbers through the current integer reference.
  * This is a software regression check, not a waveform or hardware timing test.
  */
final class AnimationTraceSpec extends AnyFreeSpec {
  private val assets = {
    val starts = Seq(Paths.get("").toAbsolutePath) ++
      sys.env.get("MILL_WORKSPACE_ROOT").map(Paths.get(_)) ++
      sys.env.get("PWD").map(Paths.get(_))
    starts.iterator.flatMap(start =>
      Iterator.iterate(start)(_.getParent).takeWhile(_ != null)
    ).map(_.resolve("docs/source/_static/learning"))
      .find(path => Files.isRegularFile(path.resolve("steane-trace.json")))
      .getOrElse(throw new IllegalStateException("Cannot find the checked-in animation fixtures"))
  }
  private def read(name: String): ujson.Value = ujson.read(Files.readString(assets.resolve(name)))
  private def ints(value: ujson.Value): Vector[Int] = value.arr.map(_.num.toInt).toVector
  private def bits(values: Seq[Boolean]): Vector[Int] = values.map(b => if (b) 1 else 0).toVector

  for (fixture <- Seq("steane", "uniform"); mode <- Seq("vanilla", "relay")) {
    s"$fixture $mode animation matches the current integer reference" in {
      val problem = read(s"$fixture-problem.json")
      val trace = read(s"$fixture-trace.json")
      assert(trace("schema").str == "chipsldpc.documentation-trace.v1")
      val captured = trace("decoders").arr.find(_("name").str == mode).get
      val relay = mode == "relay"
      val n = problem("n").num.toInt
      val rows = problem("row_ones").arr.map(ints).toVector
      val priors = ints(problem("prior"))
      val syndrome = ints(problem("syndrome")).map(_ != 0)
      val nodes = TannerNodeGraphs.from(TannerGraph.fromRows(n, rows))
      val q = if (relay) RelayDefaults.paperQ else RelayDefaults.q
      val scale = RelayDefaults.scale
      val r = problem("relay")
      val relayConfig = RelayBpConfig(nodes,
        initialIterations = r("initial_iterations").num.toInt,
        relayIterations = r("relay_iterations").num.toInt,
        maximumLegs = r("maximum_legs").num.toInt,
        solutionTarget = r("solution_target").num.toInt,
        seedOffset = r("seed_offset").num.toInt)
      val vanillaConfig = VanillaBpConfig(nodes, problem("iterations").num.toInt)
      val betas = Reference.lfsrBeta(n, relayConfig.maximumLegs, relayConfig.seedOffset)
      assert(captured("quantization")("magnitude_bits").num.toInt == q.magnitudeBits)
      assert(captured("quantization")("accumulator_bits").num.toInt == q.accumulatorBits)
      assert(ints(trace("input")("prior")) == priors)
      assert(ints(trace("input")("syndrome")) == bits(syndrome))
      assert(trace("input")("row_ones").arr.map(ints).toVector == rows)
      assert(trace("graph")("checks").num.toInt == nodes.graph.checkCount)
      assert(trace("graph")("variables").num.toInt == n)
      trace("graph")("edges").arr.zip(nodes.connections).foreach { case (edge, actual) =>
        assert(ints(ujson.Arr(edge("id"), edge("check"), edge("variable"),
          edge("check_port"), edge("variable_port"))) ==
          Vector(actual.edgeId, actual.checkId, actual.variableId, actual.checkPort, actual.variablePort))
      }
      assert(trace("graph")("edges").arr.size == nodes.graph.edgeCount)

      val initial = Reference.initialize(nodes, priors, q)
      var state = initial
      var leg = 0
      var local = 0
      var solutions = 0
      var bestScore = Option.empty[Int]
      var finished = false
      val steps = captured("steps").arr
      steps.zipWithIndex.foreach { case (step, index) =>
        withClue(s"iteration ${index + 1}: ") {
          assert(!finished, "trace continues after the decoder should stop")
          local += 1
          def vector(name: String, actual: Seq[Int]): Unit =
            assert(ints(step(name)) == actual.toVector, name)
          assert(step("leg").num.toInt == leg)
          assert(step("local_iteration").num.toInt == local)
          assert(step("total_iteration").num.toInt == index + 1)
          // These fields describe the animation's nominal schedule only.
          assert(step("cnu_cycle").num.toInt == 2 * index + 1)
          assert(step("vnu_cycle").num.toInt == 2 * index + 2)
          vector("previous_marginal", state.marginal)
          vector("input_v2c", state.v2c.map(_.signed))
          if (relay) vector("beta_int", betas(leg))
          else assert(step("beta_int") == ujson.Null)
          val bias = if (relay) priors.indices.map(i =>
            Reference.relayBias(priors(i), state.marginal(i), betas(leg)(i), relayConfig.format, q)
          ).toVector else priors
          vector("bias", bias)
          val control = local.min((1 << scale.controlBits) - 1)
          val checks = nodes.checks.map { check =>
            val input = check.edges.map(edge => state.v2c(edge.edgeId))
            val raw = Reference.twoMin(input.map(_.magnitude))
            assert(ints(step("raw_minima")(check.checkId)) == Vector(raw.first, raw.second))
            val result = Reference.check(input, syndrome(check.checkId), control,
              CheckConfig(check.degree, q, scale))
            assert(ints(step("scaled_minima")(check.checkId)) ==
              Vector(result.minima.first, result.minima.second))
            result
          }
          val messages = nodes.connections.map { edge =>
            val result = checks(edge.checkId)
            val meta = result.edges(edge.checkPort)
            Reference.CheckMessage(result.minima, meta.sign, meta.useSecond).signed
          }
          vector("c2v", messages)
          vector("total", nodes.variables.map(node =>
            bias(node.variableId) + node.edges.map(edge => messages(edge.edgeId)).sum))
          val next = Reference.iterate(nodes, state, syndrome, bias, control, q, scale)
          vector("computed_v2c", next.v2c.map(_.signed))
          vector("marginal", next.marginal)
          vector("decision", bits(next.decision))
          val residual = Reference.residual(nodes, next, syndrome)
          vector("residual", bits(residual))
          val converged = !residual.contains(true)
          assert(step("converged").bool == converged)
          val score = priors.zip(next.decision).collect { case (prior, true) => prior }.sum
          val wins = converged && bestScore.forall(score < _)
          assert(step("candidate_score").num.toInt == score)
          assert(step("candidate_wins").bool == wins)
          if (converged) solutions += 1
          if (wins) bestScore = Some(score)
          val limit = if (!relay) vanillaConfig.iterations
            else if (leg == 0) relayConfig.initialIterations else relayConfig.relayIterations
          val legEnd = converged || local == limit
          assert(step("leg_end").bool == legEnd)
          finished = legEnd && (!relay || solutions >= relayConfig.solutionTarget || leg + 1 == relayConfig.maximumLegs)
          val restart = legEnd && !finished
          assert(step("restart_messages").bool == restart)
          state = if (restart) next.copy(v2c = initial.v2c) else next
          vector("committed_v2c", state.v2c.map(_.signed))
          if (restart) { leg += 1; local = 0 }
        }
      }
      assert(finished, "trace ends before the decoder stops")
      val outcome = if (relay) Reference.runRelay(relayConfig, priors, syndrome, betas)
        else Reference.runVanilla(vanillaConfig, priors, syndrome)
      val result = captured("result")
      assert(result("success").bool == outcome.success)
      assert(ints(result("correction")) == bits(outcome.correction))
      assert(ints(result("marginal")) == outcome.state.marginal)
      assert(ints(result("residual")) == bits(outcome.residual))
      assert(result("total_iterations").num.toInt == outcome.iterations)
      assert(result("legs_executed").num.toInt == outcome.legs)
      assert(result("solutions_found").num.toInt == outcome.solutions)
      assert(outcome.iterations == steps.size)
      val predicted = problem("logical_ones").arr.map { row =>
        ints(row).count(i => outcome.correction(i)) % 2
      }.toVector
      assert(ints(result("predicted_observables")) == predicted)
      val logicalMatch = predicted == ints(problem("actual_observables"))
      assert(result("logical_match").bool == logicalMatch)
      assert(result("logical_success").bool == (outcome.success && logicalMatch))
    }
  }
}
