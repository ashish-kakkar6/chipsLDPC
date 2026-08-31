Readme
=======================

## Getting started
Forked from [Chisel3](https://www.chisel-lang.org/) project template
### Dependencies

#### JDK 11 or newer

Chisel reccomends Java 11 or later LTS releases. You can install the prebuilt binaries from [Adoptium](https://adoptium.net/).

#### SBT or mill

SBT can be downloaded it [here](https://www.scala-sbt.org/download.html).
Mill is another Scala/Java build tool preferred by Chisel's developers.
This repository includes a bootstrap script `./mill` so that no installation is necessary.

#### Verilator

The test with `svsim` needs Verilator installed.
See Verilator installation instructions [here](https://verilator.org/guide/latest/install.html).

### How to get started


You can run the included test with:
```sh
sbt test
```
or

```sh
./mill chipsLDPC.test
```

* Use packages and following conventions for [structure](https://www.scala-sbt.org/1.x/docs/Directories.html) and [naming](http://docs.scala-lang.org/style/naming-conventions.html)
* Read more about testing in SBT in the [SBT docs](https://www.scala-sbt.org/1.x/docs/Testing.html)
* This template includes a [test dependency](https://www.scala-sbt.org/1.x/docs/Library-Dependencies.html#Per-configuration+dependencies) on [ScalaTest](https://www.scalatest.org/). This, coupled with `svsim` (included with Chisel) and `verilator`, are a starting point for testing Chisel generators.
  * You can remove this dependency in the build.sbt file if you want to
