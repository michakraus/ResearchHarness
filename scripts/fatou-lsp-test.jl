#!/usr/bin/env julia
#
# Checks for fatou-lsp.jl, on the system it runs on. Run after any change to it:
#
#   julia --startup-file=no scripts/fatou-lsp-test.jl
#
# `fatou_binary` is checked on two fixture PATHs under mktempdir(): a native `fatou`, and an npm
# prefix whose `bin/fatou` links to the node wrapper of `fatou-cli` beside the platform binary.
# The client itself is checked against the real `fatou` on the PATH, which CI installs; where none
# is, that testset prints one line and is skipped.

include(joinpath(@__DIR__, "fatou-lsp.jl"))
using .FatouLSP
using Test

"Write an executable `/bin/sh` script."
function executable(path, body = "exit 0\n")
    mkpath(dirname(path))
    write(path, "#!/bin/sh\n" * body)
    chmod(path, 0o755)
    return path
end

"`fatou_binary()` with only `dir` on the PATH and no FATOU_LSP_BIN."
binary_on(dir) = withenv(FatouLSP.fatou_binary, "PATH" => dir, "FATOU_LSP_BIN" => nothing)

@testset "fatou-lsp.jl" begin
    @testset "fatou_binary: a native fatou on the PATH is returned" begin
        bin = joinpath(mktempdir(), "bin")
        native = executable(joinpath(bin, "fatou"))
        @test binary_on(bin) == native
    end

    @testset "fatou_binary: under an npm prefix, the platform binary" begin
        prefix = mktempdir()
        package = joinpath(prefix, "lib", "node_modules", "fatou-cli")
        wrapper = executable(joinpath(package, "bin", "fatou.js"))
        platform = executable(joinpath(package, "node_modules", "@fatou-cli", "fixture-arch", "fatou"))
        mkpath(joinpath(prefix, "bin"))
        symlink(wrapper, joinpath(prefix, "bin", "fatou"))
        @test binary_on(joinpath(prefix, "bin")) == platform
    end

    if Sys.which("fatou") === nothing
        println("skip  the client against the real fatou: no fatou on the PATH")
    else
        @testset "the client against the real fatou" begin
            dir = realpath(mktempdir())
            file = joinpath(dir, "Fixture.jl")
            write(file, """
                module Fixture

                double(x) = 2x

                end
                """)
            io = lsp_open()
            try
                initialize(io, dir)
                symbols = document_symbol(io, file)
                @test any(s -> s["name"] == "double" && s["kind"] == 12, symbols)
            finally
                @test lsp_close(io)
            end
        end
    end
end
