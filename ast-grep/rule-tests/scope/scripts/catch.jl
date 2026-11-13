try
    f()
catch MethodError
    nothing
end
try
    f()
catch e
    nothing
end
