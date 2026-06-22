{ lib
, python3Packages
, ...
}:

python3Packages.buildPythonApplication {
  pname = "magi";
  version = "0.1.0";
  pyproject = true;

  src = ../.;

  build-system = with python3Packages; [
    hatchling
  ];

  dependencies = with python3Packages; [
    openai
    rich
  ];

  nativeCheckInputs = with python3Packages; [
    pytestCheckHook
    pytest-asyncio
  ];

  pythonImportsCheck = [ "magi" "magi.cli" "magi.config" "magi.deliberation" ];

  passthru.homeManagerModule = ./module.nix;

  meta = with lib; {
    description = "Three-agent MAGI deliberation system, OpenAI-compatible across providers";
    homepage = "https://github.com/Nairu/magi";
    license = licenses.mit;
    mainProgram = "magi";
    platforms = platforms.unix;
  };
}
