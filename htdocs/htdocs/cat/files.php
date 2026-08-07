<?php
header('Content-Type: application/json');

$data_dir = "C:/cat/data/temporary";
$files = array_diff(scandir($data_dir), array('..', '.')); // 현재 디렉토리의 파일 목록 가져오기

// 파일 목록을 JSON 형식으로 반환
echo json_encode(array_values($files));
?>
