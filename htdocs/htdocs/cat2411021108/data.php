<?php
header('Content-Type: text/plain');

if (isset($_GET['line_number'])) {
    $line_number = basename($_GET['line_number']); // 보안상의 이유로 basename 사용
    $file_path = "C:/cat/data/temporary/{$line_number}";

    if (file_exists($file_path)) {
        // 파일 내용을 읽어서 출력
        readfile($file_path);
    } else {
        echo "파일을 찾을 수 없습니다.";
    }
} else {
    echo "라인 번호가 지정되지 않았습니다.";
}
?>
