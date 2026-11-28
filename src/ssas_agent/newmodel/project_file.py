"""The Visual Studio 2019 project file (.smproj) for a new model: the minimum that opens Model.bim.

It has no deployment server, no user settings and no build output. Those are set by the person who
opens the project in Visual Studio. The file uses CRLF line breaks, as Visual Studio does.
"""

from __future__ import annotations

PROJECT_EXTENSION = ".smproj"
MODEL_FILE_NAME = "Model.bim"
LINE_BREAK = "\r\n"
PROJECT_GUID_PLACEHOLDER = "__PROJECT_GUID__"
PROJECT_NAME_PLACEHOLDER = "__PROJECT_NAME__"

_TEMPLATE = r"""<Project ToolsVersion="4.0" DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <Configuration Condition=" '$(Configuration)' == '' ">Development</Configuration>
    <SchemaVersion>2.0</SchemaVersion>
    <ProjectGuid>{__PROJECT_GUID__}</ProjectGuid>
    <OutputType>Exe</OutputType>
    <RootNamespace>MyRootNamespace</RootNamespace>
    <AssemblyName>MyAssemblyName</AssemblyName>
    <EnableUnmanagedDebugging>false</EnableUnmanagedDebugging>
    <OutputPath>bin\</OutputPath>
    <Name>__PROJECT_NAME__</Name>
  </PropertyGroup>
  <ItemGroup />
  <ItemGroup>
    <Compile Include="Model.bim">
      <SubType>Code</SubType>
    </Compile>
  </ItemGroup>
  <Import Project="$(MSBuildExtensionsPath)\Business Intelligence Semantic Model\1.0\Microsoft.AnalysisServices.VSHostBuilder.targets" />
</Project>
"""


def project_file_text(project_name: str, project_guid: str) -> str:
    """Return the .smproj text with CRLF line breaks. The GUID must be in the 8-4-4-4-12 form."""
    text = _TEMPLATE.replace(PROJECT_GUID_PLACEHOLDER, project_guid).replace(PROJECT_NAME_PLACEHOLDER, project_name)
    return text.replace("\n", LINE_BREAK)
